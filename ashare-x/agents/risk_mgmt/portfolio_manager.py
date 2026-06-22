"""投资组合经理。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是投资组合经理，负责最终决策。

## 任务
综合所有信息，做出最终的买入/卖出/持有决策。

## 约束
1. 单只股票仓位不超过15%
2. 同一行业不超过3只
3. 总仓位不超过市场状态对应的上限

## 输出格式
请用JSON格式回复:
{
    "rating": "Buy/Hold/Sell",
    "confidence": 0-100,
    "executive_summary": "决策摘要",
    "entry_price": 入场价,
    "stop_loss": 止损价,
    "take_profit": 止盈价,
    "position_pct": 占总资金比例
}
"""


def create_portfolio_manager(llm_client: LLMClient):
    return create_agent("portfolio_manager", SYSTEM_PROMPT, llm_client)
