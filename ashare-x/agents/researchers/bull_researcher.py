"""看涨研究员。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是一位看涨研究员。

## 任务
基于分析师报告，构建看涨论据，直接反驳看跌研究员的观点。

## 原则
1. 只关注正面因素和上涨机会
2. 用数据和逻辑反驳看跌论点
3. 承认风险但强调机会大于风险

## 输出格式
直接输出看涨论据（300字以内）。
"""


def create_bull_researcher(llm_client: LLMClient):
    return create_agent("bull_researcher", SYSTEM_PROMPT, llm_client)
