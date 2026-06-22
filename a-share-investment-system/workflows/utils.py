"""超级工作流 — 通用工具函数"""

from typing import Any


class AbortWorkflowException(Exception):
    """工作流中止异常 — 捕获后立即终止节点并返回"""


def check_abort(state: dict):
    """检查是否应中止,是则抛出 AbortWorkflowException 立即终止"""
    if state.get("aborted", False):
        raise AbortWorkflowException("用户中止工作流")
    abort_fn = state.get("_abort_check")
    if callable(abort_fn) and abort_fn():
        state["aborted"] = True
        raise AbortWorkflowException("用户中止工作流")


def _log(state: dict[str, Any], msg: str):
    """向状态中追加日志"""
    if "logs" not in state:
        state["logs"] = []
    state["logs"].append(msg)
