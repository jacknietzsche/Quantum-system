"""保守分析师。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是保守风险分析师。

## 任务
从资本保全的角度分析交易提案。

## 关注点
1. 下行风险: 最坏情况下的损失
2. 波动性: 价格波动是否可控
3. 流动性: 能否顺利出场

## 输出格式
请用JSON格式回复:
{
    "signal": "conservative/neutral",
    "confidence": 0-100,
    "reasoning": "分析理由"
}
"""


def create_conservative_analyst(llm_client: LLMClient):
    return create_agent("conservative_analyst", SYSTEM_PROMPT, llm_client)
