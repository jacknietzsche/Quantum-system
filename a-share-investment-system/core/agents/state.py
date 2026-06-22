"""Agent状态定义 — 参考 TradingAgents-AShare 的 agent_states.py"""

from typing import Any

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class AnalystOutput(TypedDict, total=False):
    analysis: str
    confidence: float
    signals: dict[str, Any]


class AgentState(TypedDict, total=False):
    company_of_interest: str
    trade_date: str
    messages: list[Any]
    market_report: str | None
    fundamentals_report: str | None
    news_report: str | None
    research_debate_state: dict | None
    trader_plan: dict | None
    risk_debate_state: dict | None
    final_decision: dict | None
    iteration: int
