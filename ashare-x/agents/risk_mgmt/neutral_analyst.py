"""中性分析师。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是中性风险分析师。

## 任务
从平衡视角分析交易提案。

## 关注点
1. 风险收益比: 潜在收益与风险的比值
2. 概率分布: 成功和失败的概率
3. 综合评估: 平衡各方因素

## 输出格式
请用JSON格式回复:
{
    "signal": "neutral/balanced",
    "confidence": 0-100,
    "reasoning": "分析理由"
}
"""


def create_neutral_analyst(llm_client: LLMClient):
    return create_agent("neutral_analyst", SYSTEM_PROMPT, llm_client)
