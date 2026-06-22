"""条件路由（辩论终止判断）。

设计依据: S06 §6.3, experiments exp4.3。
多空辩论和风险辩论的终止条件。
使用独立的轮次计数器，避免共享debate_messages导致的计数错误。
"""

from __future__ import annotations

from typing import Literal

from core.state import AgentState


def should_continue_investment_debate(state: AgentState) -> Literal["continue", "end"]:
    """
    多空辩论终止条件:
    1. 达到最大轮次 → 结束
    2. Token超预算 → 紧急结束
    """
    rounds = state.get("investment_debate_rounds", 0)

    max_rounds = (
        state.get("config", {}).get("debate", {}).get("investment", {}).get("max_rounds", 2)
    )
    if rounds >= max_rounds:
        return "end"

    budget_snapshot = state.get("budget_snapshot", {})
    if budget_snapshot.get("should_fast_mode", False):
        return "end"

    return "continue"


def should_continue_risk_debate(state: AgentState) -> Literal["continue", "end"]:
    """
    风险辩论终止条件:
    1. 达到最大轮次 → 结束
    2. Token超预算 → 紧急结束
    """
    rounds = state.get("risk_debate_rounds", 0)

    max_rounds = state.get("config", {}).get("debate", {}).get("risk", {}).get("max_rounds", 2)
    if rounds >= max_rounds:
        return "end"

    budget_snapshot = state.get("budget_snapshot", {})
    if budget_snapshot.get("should_fast_mode", False):
        return "end"

    return "continue"


def route_after_pm(state: AgentState) -> Literal["with_masters", "final"]:
    """组合经理决策后，是否进入大师视角。"""
    if state.get("config", {}).get("features", {}).get("enable_masters", False):
        return "with_masters"
    return "final"
