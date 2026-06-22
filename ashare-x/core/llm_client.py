"""LLM客户端：Provider工厂 + 重试 + Token计数 + 结构化输出。

设计依据: S15, experiments exp5.1/exp5.4/exp5.5。
支持DeepSeek/Qwen/GLM，OpenAI兼容API。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel

from core.config import Config
from core.exceptions import LLMRateLimitError, LLMResponseError, LLMTimeoutError

# LLM模块日志
logger = logging.getLogger("ashare-x.core.llm")


class TokenCounter:
    """Token使用追踪 + 预算管理（三级降级）。"""

    # DeepSeek定价: 输入¥1/M tokens, 输出¥2/M tokens（近似）
    COST_PER_1K_TOKENS = 0.002  # RMB

    def __init__(self, daily_budget: int = 400000, monthly_budget_rmb: float = 100):
        self.daily_budget = daily_budget
        self.monthly_budget_rmb = monthly_budget_rmb
        self.daily_used = 0
        self.monthly_used_rmb = 0.0
        self.per_stock: dict[str, int] = {}

    def record(self, agent: str, ticker: str, tokens: int):
        self.daily_used += tokens
        self.per_stock[ticker] = self.per_stock.get(ticker, 0) + tokens
        self.monthly_used_rmb += tokens * self.COST_PER_1K_TOKENS

    def remaining(self) -> int:
        return max(0, self.daily_budget - self.daily_used)

    def should_warn(self) -> bool:
        """一级预警: 预算使用超过80%"""
        return self.daily_used >= self.daily_budget * 0.8

    def should_fast_mode(self) -> bool:
        """二级降级: 预算使用超过90%，切换到快速模式"""
        return self.daily_used >= self.daily_budget * 0.9

    def should_stop(self) -> bool:
        """三级停止: 预算使用超过120%，停止LLM调用"""
        return self.daily_used >= self.daily_budget * 1.2

    def stock_remaining(self, ticker: str, limit: int = 25000) -> int:
        return max(0, limit - self.per_stock.get(ticker, 0))

    def snapshot(self) -> dict[str, Any]:
        """返回当前预算快照。"""
        return {
            "daily_used": self.daily_used,
            "daily_budget": self.daily_budget,
            "monthly_used_rmb": round(self.monthly_used_rmb, 2),
            "monthly_budget_rmb": self.monthly_budget_rmb,
            "remaining_tokens": self.remaining(),
            "usage_pct": round(self.daily_used / self.daily_budget * 100, 1)
            if self.daily_budget else 0,
            "total_tokens": self.daily_used,
            "level": "warn" if self.should_warn() and not self.should_fast_mode()
                     else "fast" if self.should_fast_mode() and not self.should_stop()
                     else "stop" if self.should_stop() else "ok",
        }


class LLMResponse:
    """LLM响应封装。"""

    def __init__(
        self,
        content: str,
        tokens: int = 0,
        latency_ms: float = 0,
        model: str = "",
        parsed: dict | None = None,
    ):
        self.content = content
        self.tokens = tokens
        self.latency_ms = latency_ms
        self.model = model
        self.parsed = parsed


class LLMClient:
    """统一LLM调用入口。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        monthly_budget = self.config.get("llm.monthly_budget_rmb", 100)
        self.counter = TokenCounter(
            daily_budget=self.config.get("token_budget.daily_total", 400000),
            monthly_budget_rmb=monthly_budget,
        )
        self._clients: dict[str, Any] = {}

    def get_budget_snapshot(self) -> dict[str, Any]:
        """返回当前Token/预算消耗快照，供前端显示。"""
        return self.counter.snapshot()

    def _get_client(self, provider: str = "deepseek"):
        """获取OpenAI兼容客户端（懒加载）。"""
        if provider not in self._clients:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError("需要安装openai: pip install openai") from exc

            api_key = self.config.get(f"llm.{provider}.api_key", "")
            base_url = self.config.get(
                f"llm.{provider}.base_url",
                "https://api.deepseek.com",
            )
            self._clients[provider] = OpenAI(api_key=api_key, base_url=base_url)
        return self._clients[provider]

    def complete(
        self,
        messages: list[dict],
        model_tier: str = "quick",
        agent_name: str = "unknown",
        ticker: str = "",
        **kwargs,
    ) -> LLMResponse:
        """调用LLM（带重试 + 预算降级）。"""
        # 三级预算降级检查
        if self.counter.should_stop():
            logger.warning(
                "Token预算超限(%d/%d)，跳过LLM调用",
                self.counter.daily_used, self.counter.daily_budget,
            )
            return LLMResponse(
                content="⚠ 预算超限，分析已降级。请调整月度预算或减少分析次数。",
                tokens=0,
                model="budget-stopped",
            )

        # 二级降级: 切换到quick tier（轻量模型）
        if self.counter.should_fast_mode() and model_tier == "deep":
            logger.info("预算达90%%，降级到快速模式")
            model_tier = "quick"

        # 预算预警
        if self.counter.should_warn():
            logger.warning("Token预算预警: 已用%d/%d (%.1f%%)",
                          self.counter.daily_used, self.counter.daily_budget,
                          self.counter.daily_used / self.counter.daily_budget * 100)

        provider = self.config.get(f"llm.{model_tier}.provider", "deepseek")
        model = self.config.get(f"llm.{model_tier}.model", "deepseek-chat")
        client = self._get_client(provider)

        logger.info(
            "LLM调用: agent=%s, ticker=%s, model=%s/%s, messages=%d条",
            agent_name,
            ticker,
            provider,
            model,
            len(messages),
        )
        logger.debug("LLM请求: %s", json.dumps(messages[:1], ensure_ascii=False)[:200])

        for attempt in range(3):
            try:
                start = time.time()
                response = client.chat.completions.create(model=model, messages=messages, **kwargs)
                latency = (time.time() - start) * 1000
                usage = response.usage
                tokens = usage.total_tokens if usage else 0
                self.counter.record(agent_name, ticker, tokens)

                logger.info(
                    "LLM响应: agent=%s, tokens=%d, latency=%.0fms, model=%s",
                    agent_name,
                    tokens,
                    latency,
                    response.model,
                )
                logger.debug("LLM响应内容: %s", response.choices[0].message.content[:200])

                return LLMResponse(
                    content=response.choices[0].message.content,
                    tokens=tokens,
                    latency_ms=latency,
                    model=response.model,
                )
            except Exception as e:
                logger.warning(
                    "LLM调用失败 (attempt %d/3): %s - %s",
                    attempt + 1,
                    type(e).__name__,
                    str(e)[:200],
                )
                if "timeout" in str(e).lower():
                    raise LLMTimeoutError(str(e)) from e
                if "429" in str(e) or "rate" in str(e).lower():
                    raise LLMRateLimitError(str(e)) from e
                if attempt < 2:
                    delay = 2**attempt
                    logger.info("重试等待 %ds...", delay)
                    time.sleep(delay)
                else:
                    raise

        raise LLMResponseError("所有重试失败")

    def complete_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        agent_name: str = "unknown",
        ticker: str = "",
        **kwargs,
    ) -> LLMResponse:
        """结构化输出（四阶段策略）。"""
        # 策略1: 直接调用 + JSON解析  # noqa: ERA001
        try:
            resp = self.complete(messages, agent_name=agent_name, ticker=ticker, **kwargs)
            parsed = self._try_parse_json(resp.content, schema)
            if parsed:
                resp.parsed = parsed
                return resp
        except Exception:
            pass

        # 策略2: Prompt引导JSON  # noqa: ERA001
        json_messages = [
            *messages,
            {"role": "system", "content": f"请严格以JSON格式输出: {schema.model_json_schema()}"},
        ]
        try:
            resp = self.complete(json_messages, agent_name=agent_name, ticker=ticker, **kwargs)
            parsed = self._try_parse_json(resp.content, schema)
            if parsed:
                resp.parsed = parsed
                return resp
        except Exception:
            pass

        # 策略3: Free-text正则提取  # noqa: ERA001
        try:
            resp = self.complete(messages, agent_name=agent_name, ticker=ticker, **kwargs)
            parsed = self._extract_from_text(resp.content, schema)
            if parsed:
                resp.parsed = parsed
                return resp
        except Exception:
            pass

        # 策略4: 默认值  # noqa: ERA001
        default = self._create_default(schema)
        return LLMResponse(content="", parsed=default, model="fallback")

    def _try_parse_json(self, text: str, schema: type[BaseModel]) -> dict | None:
        """尝试从文本中解析JSON并验证schema。"""
        try:
            # 去掉markdown代码块
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean.rsplit("```", 1)[0]
            clean = clean.strip()

            # 尝试直接解析
            data = json.loads(clean)
            obj = schema.model_validate(data)
            return obj.model_dump()
        except Exception:
            # 尝试正则提取JSON
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    obj = schema.model_validate(data)
                    return obj.model_dump()
                except Exception:
                    pass
        return None

    def _extract_from_text(self, text: str, schema: type[BaseModel]) -> dict | None:
        """从free-text中提取字段。"""
        result = {}
        for field_name, field_info in schema.model_fields.items():
            annotation = field_info.annotation
            # Literal类型
            if (
                hasattr(annotation, "__origin__")
                and annotation.__origin__ is type(annotation).__origin__
            ):
                for allowed in getattr(annotation, "__args__", []):
                    if isinstance(allowed, str) and allowed.lower() in text.lower():
                        result[field_name] = allowed
                        break
            # 数字字段
            if annotation in (int, float):
                patterns = {
                    "confidence": r"(?:置信度|confidence)[:\s]*(\d+)",
                    "entry_price": r"(?:入场价|entry)[:\s]*(\d+\.?\d*)",
                    "stop_loss": r"(?:止损)[:\s]*(\d+\.?\d*)",
                }
                if field_name in patterns:
                    match = re.search(patterns[field_name], text, re.IGNORECASE)
                    if match:
                        result[field_name] = float(match.group(1))
        return result if result else None

    def _create_default(self, schema: type[BaseModel]) -> dict:
        """根据schema字段类型自动生成默认值。"""
        defaults = {}
        for name, info in schema.model_fields.items():
            ann = info.annotation
            if ann is str:
                defaults[name] = ""
            elif ann is int:
                defaults[name] = 0
            elif ann is float:
                defaults[name] = 0.0
            elif hasattr(ann, "__origin__") and ann.__origin__ is list:
                defaults[name] = []
            elif hasattr(ann, "__args__"):
                args = ann.__args__
                if args and isinstance(args[0], str):
                    defaults[name] = args[0]
                else:
                    defaults[name] = None
            else:
                defaults[name] = None
        return defaults
