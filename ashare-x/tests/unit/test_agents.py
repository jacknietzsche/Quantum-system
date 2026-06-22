"""Phase 3 LLM+Agent层测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.base import create_agent
from agents.masters.selector import select_masters
from core.llm_client import LLMResponse, TokenCounter


class TestTokenCounter:
    def test_record_and_remaining(self):
        counter = TokenCounter(daily_budget=100000)
        counter.record("agent1", "600519", 5000)
        assert counter.remaining() == 95000
        assert counter.per_stock["600519"] == 5000

    def test_fast_mode_threshold(self):
        counter = TokenCounter(daily_budget=100000)
        counter.record("agent1", "600519", 90000)
        assert counter.should_fast_mode() is True

    def test_stock_remaining(self):
        counter = TokenCounter()
        counter.record("agent1", "600519", 10000)
        assert counter.stock_remaining("600519") == 15000
        assert counter.stock_remaining("000001") == 25000


class TestLLMResponse:
    def test_response_fields(self):
        resp = LLMResponse(content="test", tokens=100, latency_ms=50, model="deepseek-chat")
        assert resp.content == "test"
        assert resp.tokens == 100
        assert resp.model == "deepseek-chat"


class TestAgentFactory:
    def test_create_agent_returns_callable(self):
        mock_llm = MagicMock()
        agent = create_agent("test_agent", "Test prompt", mock_llm)
        assert callable(agent)

    def test_agent_node_returns_dict(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(content="test response")
        agent = create_agent("test_agent", "Test prompt", mock_llm)
        result = agent({"ticker": "600519"})
        assert "test_agent_report" in result


class TestMasterSelector:
    def test_select_for_value_stock(self):
        profile = {"pe_ratio": 15, "roe": 25, "volatility": 0.2, "revenue_growth": 0.1}
        masters = select_masters(profile)
        assert len(masters) <= 3
        assert "buffett" in masters or "munger" in masters

    def test_select_for_growth_stock(self):
        profile = {"pe_ratio": 50, "roe": 20, "volatility": 0.4, "revenue_growth": 0.35}
        masters = select_masters(profile)
        assert len(masters) <= 3
        assert "wood" in masters or "fisher" in masters

    def test_select_for_volatile_stock(self):
        profile = {"pe_ratio": 10, "roe": 10, "volatility": 0.5, "revenue_growth": 0.05}
        masters = select_masters(profile)
        assert len(masters) <= 3
