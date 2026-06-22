"""状态传播工具。

设计依据: S06 §6.2。
LangGraph状态合并辅助函数。
"""

from __future__ import annotations

from core.state import AgentState


def merge_signals(state: AgentState, agent_name: str, signal: dict) -> AgentState:
    """合并分析师信号到state。"""
    signals = state.get("analyst_signals", {})
    signals[agent_name] = signal
    return {"analyst_signals": signals}


def append_debate_message(state: AgentState, message: dict) -> AgentState:
    """追加辩论消息。"""
    messages = state.get("debate_messages", [])
    messages.append(message)
    return {"debate_messages": messages}


def clear_messages(state: AgentState) -> AgentState:
    """清理消息（阶段转换时）。"""
    return {"messages": []}
