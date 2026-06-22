"""Agent 共享工具函数 — 从 5 个 agent 模块提取的重复代码"""

from __future__ import annotations


def get_language_instruction() -> str:
    """返回中文指令后缀"""
    return "\n请用中文撰写报告."


def get_instrument_context(state: dict) -> str:
    """从状态中提取标的上下文"""
    stock_code = state.get("stock_code", "")
    stock_name = state.get("stock_name", "")
    if stock_code or stock_name:
        return f"\n当前分析标的: {stock_name} ({stock_code})"
    return ""


# 保持旧名称兼容
_get_language_instruction = get_language_instruction
_get_instrument_context = get_instrument_context
