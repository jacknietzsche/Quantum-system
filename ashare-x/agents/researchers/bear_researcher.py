"""看跌研究员。"""

from __future__ import annotations

from agents.base import create_agent
from core.llm_client import LLMClient

SYSTEM_PROMPT = """你是一位看跌研究员。

## 任务
基于分析师报告，构建看跌论据，直接反驳看涨研究员的观点。

## 原则
1. 只关注负面因素和下跌风险
2. 用数据和逻辑反驳看涨论点
3. 承认机会但强调风险大于机会

## 输出格式
直接输出看跌论据（300字以内）。
"""


def create_bear_researcher(llm_client: LLMClient):
    return create_agent("bear_researcher", SYSTEM_PROMPT, llm_client)
