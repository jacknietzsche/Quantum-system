"""LLM 客户端单元测试。"""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from pydantic import BaseModel

from core.config import Config
from core.exceptions import LLMRateLimitError, LLMTimeoutError
from core.llm_client import LLMClient, LLMResponse, TokenCounter


class _TestSchema(BaseModel):
    action: str = ""
    confidence: int = 0


@pytest.fixture()
def llm_config(isolated_env: Path) -> Config:
    """构造一个隔离的临时 LLM 配置。"""
    config_path = isolated_env / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "monthly_budget_rmb": 100,
                    "quick": {"provider": "deepseek", "model": "deepseek-chat"},
                    "deep": {"provider": "deepseek", "model": "deepseek-reasoner"},
                },
                "token_budget": {"daily_total": 400000},
            }
        ),
        encoding="utf-8",
    )
    Config.reset()
    return Config(config_path)


class TestTokenCounter:
    """TokenCounter 预算管理测试。"""

    def test_record_and_remaining(self):
        counter = TokenCounter(daily_budget=100)
        counter.record("agent", "600519", 30)
        assert counter.daily_used == 30
        assert counter.remaining() == 70
        assert counter.per_stock["600519"] == 30

    def test_should_warn(self):
        counter = TokenCounter(daily_budget=100)
        counter.daily_used = 80
        assert counter.should_warn() is True

    def test_should_fast_mode(self):
        counter = TokenCounter(daily_budget=100)
        counter.daily_used = 91
        assert counter.should_fast_mode() is True

    def test_should_stop(self):
        counter = TokenCounter(daily_budget=100)
        counter.daily_used = 121
        assert counter.should_stop() is True

    def test_stock_remaining(self):
        counter = TokenCounter()
        counter.per_stock["600519"] = 5000
        assert counter.stock_remaining("600519", limit=10000) == 5000
        assert counter.stock_remaining("000001", limit=10000) == 10000

    def test_snapshot_levels(self):
        counter = TokenCounter(daily_budget=100)
        assert counter.snapshot()["level"] == "ok"

        counter.daily_used = 85
        assert counter.snapshot()["level"] == "warn"

        counter.daily_used = 95
        assert counter.snapshot()["level"] == "fast"

        counter.daily_used = 130
        assert counter.snapshot()["level"] == "stop"


class TestLLMResponse:
    def test_defaults(self):
        resp = LLMResponse("hello")
        assert resp.content == "hello"
        assert resp.tokens == 0


class TestLLMClient:
    """LLMClient 调用与解析测试。"""

    def test_get_budget_snapshot(self, llm_config: Config):
        client = LLMClient(llm_config)
        snap = client.get_budget_snapshot()
        assert "daily_used" in snap
        assert snap["level"] == "ok"

    def test_budget_stop_returns_message(self, llm_config: Config):
        client = LLMClient(llm_config)
        client.counter.daily_used = client.counter.daily_budget * 2
        resp = client.complete([{"role": "user", "content": "hi"}])
        assert "预算超限" in resp.content
        assert resp.model == "budget-stopped"

    def test_fast_mode_downgrades_deep_tier(self, llm_config: Config):
        client = LLMClient(llm_config)
        client.counter.daily_used = int(client.counter.daily_budget * 0.95)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))],
            usage=MagicMock(total_tokens=5),
            model="deepseek-chat",
        )

        with patch.object(client, "_get_client", return_value=mock_client):
            resp = client.complete([{"role": "user", "content": "hi"}], model_tier="deep")

        assert resp.content == "ok"
        mock_client.chat.completions.create.assert_called_once()

    def test_complete_success(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="hello"))],
            usage=MagicMock(total_tokens=10),
            model="deepseek-chat",
        )

        with patch.object(client, "_get_client", return_value=mock_client):
            resp = client.complete([{"role": "user", "content": "hi"}])

        assert resp.content == "hello"
        assert resp.tokens == 10
        assert resp.model == "deepseek-chat"
        assert client.counter.daily_used == 10

    def test_complete_timeout_raises(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Request timeout")

        with patch.object(client, "_get_client", return_value=mock_client), pytest.raises(
            LLMTimeoutError
        ):
            client.complete([{"role": "user", "content": "hi"}])

    def test_complete_rate_limit_raises(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 rate limit")

        with patch.object(client, "_get_client", return_value=mock_client), pytest.raises(
            LLMRateLimitError
        ):
            client.complete([{"role": "user", "content": "hi"}])

    def test_complete_retries_then_fails(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("boom")

        with patch.object(client, "_get_client", return_value=mock_client), pytest.raises(
            Exception, match="boom"
        ):
            client.complete([{"role": "user", "content": "hi"}])
        assert mock_client.chat.completions.create.call_count == 3

    def test_try_parse_json_strips_markdown(self, llm_config: Config):
        client = LLMClient(llm_config)
        parsed = client._try_parse_json(
            '```json\n{"action":"BUY","confidence":85}\n```', _TestSchema
        )
        assert parsed == {"action": "BUY", "confidence": 85}

    def test_try_parse_json_regex_fallback(self, llm_config: Config):
        client = LLMClient(llm_config)
        parsed = client._try_parse_json(
            'some text {"action":"SELL","confidence":60} end', _TestSchema
        )
        assert parsed == {"action": "SELL", "confidence": 60}

    def test_extract_from_text(self, llm_config: Config):
        client = LLMClient(llm_config)
        parsed = client._extract_from_text("置信度: 80", _TestSchema)
        assert parsed == {"confidence": 80.0}

    def test_create_default(self, llm_config: Config):
        client = LLMClient(llm_config)
        defaults = client._create_default(_TestSchema)
        assert defaults == {"action": "", "confidence": 0}

    def test_complete_structured_direct_parse(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_resp = LLMResponse('{"action":"BUY","confidence":90}', tokens=5)

        with patch.object(client, "complete", return_value=mock_resp):
            resp = client.complete_structured(
                [{"role": "user", "content": "hi"}], _TestSchema
            )

        assert resp.parsed == {"action": "BUY", "confidence": 90}

    def test_complete_structured_fallback_default(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_resp = LLMResponse("not json", tokens=5)

        with patch.object(client, "complete", return_value=mock_resp), patch.object(
            client, "_extract_from_text", return_value=None
        ):
            resp = client.complete_structured(
                [{"role": "user", "content": "hi"}], _TestSchema
            )

        assert resp.parsed == {"action": "", "confidence": 0}
        assert resp.model == "fallback"

    def test_get_client_import_error(self, llm_config: Config):
        client = LLMClient(llm_config)
        with (
            patch.object(builtins, "__import__", side_effect=ImportError("no openai")),
            pytest.raises(ImportError, match="需要安装openai"),
        ):
            client._get_client()

    def test_get_client_caches_same_instance(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_openai = MagicMock()
        mock_openai.OpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            c1 = client._get_client("deepseek")
            c2 = client._get_client("deepseek")

        assert c1 is c2

    def test_complete_budget_warning(self, llm_config: Config):
        client = LLMClient(llm_config)
        client.counter.daily_used = int(client.counter.daily_budget * 0.85)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))],
            usage=MagicMock(total_tokens=5),
            model="deepseek-chat",
        )

        with patch.object(client, "_get_client", return_value=mock_client):
            resp = client.complete([{"role": "user", "content": "hi"}])

        assert resp.content == "ok"

    def test_complete_usage_none(self, llm_config: Config):
        client = LLMClient(llm_config)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))],
            usage=None,
            model="deepseek-chat",
        )

        with patch.object(client, "_get_client", return_value=mock_client):
            resp = client.complete([{"role": "user", "content": "hi"}])

        assert resp.tokens == 0

    def test_try_parse_json_invalid_returns_none(self, llm_config: Config):
        client = LLMClient(llm_config)
        assert client._try_parse_json("not json", _TestSchema) is None

    def test_extract_from_text_literal(self, llm_config: Config):
        from typing import Literal

        class LiteralSchema(BaseModel):
            action: Literal["BUY", "SELL"] = "BUY"

        client = LLMClient(llm_config)
        parsed = client._extract_from_text("recommend sell now", LiteralSchema)
        assert parsed == {"action": "SELL"}

    def test_create_default_list_and_literal(self, llm_config: Config):
        from typing import Literal

        class ComplexSchema(BaseModel):
            tags: list[str]
            action: Literal["BUY", "SELL"] = "BUY"
            ratio: float

        client = LLMClient(llm_config)
        defaults = client._create_default(ComplexSchema)
        assert defaults == {"tags": [], "action": "BUY", "ratio": 0.0}

    def test_complete_structured_json_prompt_strategy(self, llm_config: Config):
        client = LLMClient(llm_config)
        # 第一次返回无效，第二次（JSON prompt）返回有效
        responses = [
            LLMResponse("invalid", tokens=5),
            LLMResponse('{"action":"BUY","confidence":70}', tokens=5),
        ]

        with patch.object(client, "complete", side_effect=responses):
            resp = client.complete_structured(
                [{"role": "user", "content": "hi"}], _TestSchema
            )

        assert resp.parsed == {"action": "BUY", "confidence": 70}

    def test_complete_structured_regex_extract_strategy(self, llm_config: Config):
        client = LLMClient(llm_config)
        # 前两次 complete 都返回无效 JSON，第三次 free text 被正则提取
        responses = [
            LLMResponse("invalid", tokens=5),
            LLMResponse("still invalid", tokens=5),
            LLMResponse("置信度: 55", tokens=5),
        ]

        with patch.object(client, "complete", side_effect=responses):
            resp = client.complete_structured(
                [{"role": "user", "content": "hi"}], _TestSchema
            )

        assert resp.parsed == {"confidence": 55.0}
