"""主工作流定义 — 转发到 existing workflows/nodes/

完整迁移将在后续阶段完成。目前作为转发桩,为 core/ 内的调用方提供
run_super_workflow / run_analysis 两个入口。

workflows/nodes/ 的导入被延迟到对应函数调用时,以避免缺少上游生产依赖时阻断轻量入口。
"""

import os
import sys
from collections.abc import Callable
from typing import Any

# ── 兼容 workflows/ 的 import 路径 ──
_workflows_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "workflows",
)
if _workflows_dir not in sys.path:
    sys.path.insert(0, _workflows_dir)


def _lazy_import(name: str, package: str | None = None):
    """按需导入 — 避免强依赖阻断轻量入口"""
    import importlib

    try:
        return importlib.import_module(name, package)
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"Cannot import {name}: missing dependency '{e.name}'. "
            f"This is expected if optional production dependencies are not installed."
        ) from e


def _get_node_functions():
    """延迟加载 workflows/nodes/__init__ 中的全部导出。"""
    return _lazy_import("workflows.nodes")


def _get_shared():
    """延迟加载 workflows/nodes/_shared"""
    return _lazy_import("workflows.nodes._shared")


def _get_utils():
    """延迟加载 workflows.utils"""
    return _lazy_import("workflows.utils")


# ── 轻量入口 — 不依赖 workflows/nodes 的基础组件 ──


def run_analysis(code: str, date: str) -> dict[str, Any]:
    """轻量分析入口 — 直接使用 core.agents.analysts 的独立分析函数。

    不依赖 LangGraph,适合快速查看单只股票的基础面+市场+新闻评分。
    """
    from ..agents.analysts.fundamentals import analyze_fundamentals
    from ..agents.analysts.market import analyze_market
    from ..agents.analysts.news import analyze_news

    market = analyze_market(code, date)
    fundamentals = analyze_fundamentals(code, date)
    news = analyze_news(code, date)

    # 聚合评分
    scores = []
    for r in [market, fundamentals]:
        if r.get("confidence", 0) > 0 and "score" in r:
            scores.append(r["score"])
    avg_score = sum(scores) / len(scores) if scores else 50
    signal = "buy" if avg_score >= 60 else ("hold" if avg_score >= 40 else "sell")

    return {
        "market_analysis": market,
        "fundamentals_analysis": fundamentals,
        "news_analysis": news,
        "composite_score": round(avg_score, 0),
        "signal": signal,
    }


def run_workflow(
    code: str,
    date: str,
    mode: str = "standard",
    progress_callback: Callable | None = None,
    abort_check: Callable | None = None,
) -> dict[str, Any]:
    """运行完整分析流水线。

    当 mode="standard" 时使用轻量 run_analysis;
    当 mode="full" 时调用 run_super_workflow_single_stock 执行完整 LangGraph 流水线。
    """
    if mode == "full":
        # 延迟导入 — 需要安装完整的 optional dependencies
        nodes = _get_node_functions()
        return nodes.run_super_workflow_single_stock(
            code, progress_callback=progress_callback, abort_check=abort_check
        )

    # standard 模式:轻量分析
    result = run_analysis(code, date)
    result["code"] = code
    result["date"] = date
    result["mode"] = mode
    return result


# ── 转发属性(延迟加载 + __getattr__ 兼容模式)──

_NODE_NAMES = [
    "node_fetch_global_data",
    "node_data_collector",
    "node_skill_analysis_parallel",
    "node_debate_committee",
    "node_ai_hedge_fund_vote",
    "node_fincept_master_verify",
    "node_risk_control_audit",
    "node_portfolio_management",
    "node_multi_model_vote",
    "node_generate_recommendations",
    "node_generate_final_report",
    "node_push_notification",
]

_RUNNER_NAMES = [
    "build_super_workflow",
    "run_super_workflow",
    "run_super_workflow_single_stock",
    "router_risk_pass_or_not",
    "_extract_vote_stats",
]

_SHARED_NAMES = [
    "AShareSuperState",
    "create_data_bus",
    "run_hedge_fund_committee",
    "run_fincept_master_verify",
]

_UTIL_NAMES = [
    "_log",
    "check_abort",
    "AbortWorkflowException",
]


def __getattr__(name: str):
    """通过 __getattr__ 延迟转发,使 from core.graph.workflow import X 在 X 首次被访问时才触发导入。"""
    try:
        if name in _NODE_NAMES or name in _RUNNER_NAMES:
            mod = _get_node_functions()
            if hasattr(mod, name):
                return getattr(mod, name)
        if name in _SHARED_NAMES:
            mod = _get_shared()
            if hasattr(mod, name):
                return getattr(mod, name)
        if name in _UTIL_NAMES:
            mod = _get_utils()
            if hasattr(mod, name):
                return getattr(mod, name)
    except RuntimeError as e:
        # 将因缺少依赖导致的 RuntimeError 转为 AttributeError,
        # 使得 hasattr() 在缺少依赖时优雅返回 False 而非抛出异常。
        raise AttributeError(str(e)) from e
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_ALL_EXPORTS = ["run_analysis", "run_workflow"]
_ALL_EXPORTS.extend(_NODE_NAMES)
_ALL_EXPORTS.extend(_RUNNER_NAMES)
_ALL_EXPORTS.extend(_SHARED_NAMES)
_ALL_EXPORTS.extend(_UTIL_NAMES)
__all__ = _ALL_EXPORTS  # noqa: PLE0605
