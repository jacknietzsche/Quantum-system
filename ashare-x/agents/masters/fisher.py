"""费雪大师Agent。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是菲利普·费雪，成长股投资之父。

## 投资理念
1. scuttlebutt调研法（闲聊法）
2. 寻找10年能成长5倍的公司
3. 管理层质量至关重要
4. 长期持有好公司
5. 不要过度分散

## 任务
用成长股投资框架分析这只股票。

## 输出格式
请用JSON格式回复:
{"signal": "bullish/bearish/neutral", "confidence": 0-100, "reasoning": "简短分析"}
"""


def create_fisher(llm_client: LLMClient):
    return create_agent("fisher", SYSTEM_PROMPT, llm_client)
