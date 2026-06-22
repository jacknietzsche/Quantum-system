# -*- coding: utf-8 -*-
"""
实验5: LLM API调用验证
目标: 验证DeepSeek API调用、结构化输出、token计数
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# 加载.env
env_path = Path("C:/Users/21471/WorkBuddy/Trading agent and skill/a-share-investment-system/config/.env")
if env_path.exists():
    load_dotenv(env_path)
    print(f"已加载 .env: {env_path}")
else:
    print(f".env 不存在: {env_path}")

# 检查API Key
api_key = os.environ.get("DEEPSEEK_API_KEY", "")
if api_key:
    print(f"DEEPSEEK_API_KEY: {api_key[:8]}...{api_key[-4:]}")
else:
    print("DEEPSEEK_API_KEY 未设置")

print("=" * 60)

# ========== 实验5.1: DeepSeek Chat API调用 ==========
print("\n" + "=" * 60)
print("实验5.1: DeepSeek Chat API调用")
print("=" * 60)

try:
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    start = time.time()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一个A股分析师。请用中文回复。"},
            {"role": "user", "content": "分析贵州茅台(600519)的技术面，给出看涨/看跌/中性的判断，附带置信度(0-100)和理由。请用JSON格式回复：{\"signal\": \"bullish/bearish/neutral\", \"confidence\": 80, \"reasoning\": \"理由\"}"}
        ],
        temperature=0.7,
        max_tokens=500
    )

    elapsed = time.time() - start
    content = response.choices[0].message.content
    usage = response.usage

    print(f"响应时间: {elapsed:.2f}秒")
    print(f"模型: {response.model}")
    print(f"响应内容:\n{content}")
    print(f"Token使用:")
    print(f"  prompt_tokens: {usage.prompt_tokens}")
    print(f"  completion_tokens: {usage.completion_tokens}")
    print(f"  total_tokens: {usage.total_tokens}")

    # 尝试解析JSON
    try:
        # 去掉可能的markdown代码块标记
        clean_content = content.strip()
        if clean_content.startswith("```"):
            clean_content = clean_content.split("\n", 1)[1]
        if clean_content.endswith("```"):
            clean_content = clean_content.rsplit("```", 1)[0]
        clean_content = clean_content.strip()

        parsed = json.loads(clean_content)
        print(f"\nJSON解析成功:")
        print(f"  signal: {parsed.get('signal')}")
        print(f"  confidence: {parsed.get('confidence')}")
        print(f"  reasoning: {parsed.get('reasoning')[:50]}...")
        print("[PASS] DeepSeek Chat API + JSON解析成功")
    except json.JSONDecodeError as e:
        print(f"\nJSON解析失败: {e}")
        print(f"原始内容: {content}")
        print("[PARTIAL] API调用成功但JSON解析失败，需要fallback")

except Exception as e:
    print(f"[FAIL] DeepSeek API调用失败: {e}")

# ========== 实验5.2: 结构化输出（Pydantic） ==========
print("\n" + "=" * 60)
print("实验5.2: 结构化输出（Pydantic Schema）")
print("=" * 60)

try:
    from pydantic import BaseModel, Field
    from typing import Literal

    class AnalystSignal(BaseModel):
        signal: Literal["bullish", "bearish", "neutral"]
        confidence: int = Field(ge=0, le=100, description="置信度0-100")
        reasoning: str = Field(description="分析理由")

    class PortfolioDecision(BaseModel):
        rating: Literal["Buy", "Hold", "Sell"]
        confidence: float = Field(ge=0, le=100)
        executive_summary: str
        entry_price: float | None = None
        stop_loss: float | None = None
        take_profit: float | None = None
        position_pct: float | None = None

    # 测试Pydantic验证
    signal = AnalystSignal(signal="bullish", confidence=75, reasoning="技术面看涨")
    print(f"AnalystSignal验证通过: {signal.model_dump()}")

    decision = PortfolioDecision(
        rating="Buy", confidence=80,
        executive_summary="建议买入",
        entry_price=1500.0, stop_loss=1425.0, take_profit=1650.0,
        position_pct=5.0
    )
    print(f"PortfolioDecision验证通过: {decision.model_dump()}")

    # 测试验证失败
    try:
        bad_signal = AnalystSignal(signal="invalid", confidence=150, reasoning="")
        print("[FAIL] 应该验证失败但没有")
    except Exception as e:
        print(f"验证失败（预期行为）: {type(e).__name__}")

    print("[PASS] Pydantic Schema验证成功")
except Exception as e:
    print(f"[FAIL] Pydantic验证失败: {e}")

# ========== 实验5.3: 结构化输出 + Pydantic自动默认值 ==========
print("\n" + "=" * 60)
print("实验5.3: Pydantic自动默认值")
print("=" * 60)

try:
    from pydantic import BaseModel, Field
    from typing import Literal, Optional

    def create_default_response(model_class: type[BaseModel]) -> BaseModel:
        """根据字段类型自动生成默认值"""
        default_values = {}
        for field_name, field_info in model_class.model_fields.items():
            annotation = field_info.annotation
            if annotation == str:
                default_values[field_name] = "数据不足"
            elif annotation == int:
                default_values[field_name] = 0
            elif annotation == float:
                default_values[field_name] = 0.0
            elif annotation == bool:
                default_values[field_name] = False
            elif hasattr(annotation, "__origin__"):
                origin = annotation.__origin__
                if origin == list:
                    default_values[field_name] = []
                elif origin == dict:
                    default_values[field_name] = {}
                elif origin == Literal:
                    args = annotation.__args__
                    if args:
                        default_values[field_name] = args[0]
            elif hasattr(annotation, "__args__"):
                args = annotation.__args__
                inner = args[0] if args else str
                if inner == str:
                    default_values[field_name] = ""
                elif inner == float:
                    default_values[field_name] = None
                elif inner == int:
                    default_values[field_name] = None
        return model_class(**default_values)

    default_decision = create_default_response(PortfolioDecision)
    print(f"自动默认值: {default_decision.model_dump()}")
    print("[PASS] Pydantic自动默认值成功")
except Exception as e:
    print(f"[FAIL] 自动默认值失败: {e}")

# ========== 实验5.4: Token计数器 ==========
print("\n" + "=" * 60)
print("实验5.4: Token计数器")
print("=" * 60)

try:
    class TokenCounter:
        def __init__(self, daily_budget: int = 400000):
            self.daily_budget = daily_budget
            self.daily_used = 0
            self.per_stock_used = {}

        def record(self, agent: str, ticker: str, tokens: int):
            self.daily_used += tokens
            self.per_stock_used[ticker] = self.per_stock_used.get(ticker, 0) + tokens

        def remaining(self) -> int:
            return max(0, self.daily_budget - self.daily_used)

        def should_fast_mode(self) -> bool:
            return self.daily_used >= self.daily_budget * 0.9

        def stock_budget_remaining(self, ticker: str, limit: int = 25000) -> int:
            used = self.per_stock_used.get(ticker, 0)
            return max(0, limit - used)

    counter = TokenCounter(daily_budget=400000)

    # 模拟10只股票分析
    for i in range(10):
        ticker = f"60051{i}"
        counter.record("market_analyst", ticker, 1500)
        counter.record("bull_researcher", ticker, 1200)
        counter.record("bear_researcher", ticker, 1200)
        counter.record("portfolio_manager", ticker, 2000)

    print(f"10只股票分析后:")
    print(f"  日使用量: {counter.daily_used}")
    print(f"  日剩余: {counter.remaining()}")
    print(f"  使用率: {counter.daily_used/counter.daily_budget*100:.1f}%")
    print(f"  快速模式: {counter.should_fast_mode()}")
    print(f"  每股剩余: {counter.stock_budget_remaining('600510')}")

    # 测试快速模式触发
    for i in range(15):
        counter.record("portfolio_manager", f"extra_{i}", 20000)

    print(f"\n25只股票后:")
    print(f"  日使用量: {counter.daily_used}")
    print(f"  使用率: {counter.daily_used/counter.daily_budget*100:.1f}%")
    print(f"  快速模式: {counter.should_fast_mode()}")

    print("[PASS] Token计数器成功")
except Exception as e:
    print(f"[FAIL] Token计数器失败: {e}")

# ========== 实验5.5: 重试机制 ==========
print("\n" + "=" * 60)
print("实验5.5: 重试机制")
print("=" * 60)

try:
    import asyncio
    import random

    class RetryManager:
        def __init__(self, max_attempts: int = 2, base_delay: float = 1.0):
            self.max_attempts = max_attempts
            self.base_delay = base_delay

        async def execute(self, fn, fallback=None):
            last_error = None
            for attempt in range(self.max_attempts + 1):
                try:
                    return await fn()
                except Exception as e:
                    last_error = e
                    if attempt < self.max_attempts:
                        delay = self.base_delay * (2 ** attempt)
                        jitter = delay * 0.1 * (2 * random.random() - 1)
                        await asyncio.sleep(min(delay + jitter, 0.1))  # 实验用短延迟
                        continue
            if fallback:
                return fallback()
            raise last_error

    async def test_retry():
        call_count = 0

        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"模拟失败 (attempt {call_count})")
            return "成功"

        retry = RetryManager(max_attempts=2, base_delay=0.01)
        result = await retry.execute(flaky_function, fallback=lambda: "降级结果")
        return result, call_count

    result, calls = asyncio.run(test_retry())
    print(f"重试结果: {result}")
    print(f"调用次数: {calls}")
    print("[PASS] 重试机制成功")
except Exception as e:
    print(f"[FAIL] 重试机制失败: {e}")

print("\n" + "=" * 60)
print("实验5完成")
print("=" * 60)
