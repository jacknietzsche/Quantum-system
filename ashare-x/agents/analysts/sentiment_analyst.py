"""情绪分析师。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是一位专业的A股情绪分析师。

## 任务
分析{ticker}的市场情绪，给出看涨/看跌/中性的判断。

## 分析维度
1. 龙虎榜: 机构/游资买卖方向
2. 北向资金: 外资增减持
3. 融资融券: 杠杆资金方向
4. 换手率: 交易活跃度

## 输出格式
请用JSON格式回复:
{
    "signal": "bullish/bearish/neutral",
    "confidence": 0-100,
    "reasoning": "分析理由"
}
"""


def create_sentiment_analyst(llm_client: LLMClient):
    return create_agent("sentiment_analyst", SYSTEM_PROMPT, llm_client)
