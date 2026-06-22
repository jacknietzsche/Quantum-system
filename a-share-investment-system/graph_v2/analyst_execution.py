"""分析师执行计划 — 参考 TradingAgents/graph/analyst_execution.py

管理分析师节点的注册和执行顺序.
支持并发限制: analyst_concurrency_limit 控制同时运行的分析师数.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalystSpec:
    """单个分析师节点规格"""

    key: str
    agent_node: str
    tool_node: str
    clear_node: str


@dataclass
class AnalystExecutionPlan:
    """分析师执行计划"""

    specs: list[AnalystSpec] = field(default_factory=list)


# 默认分析师注册表
ANALYST_REGISTRY = {
    "market": AnalystSpec(
        key="market",
        agent_node="Market Analyst",
        tool_node="tools_market",
        clear_node="Msg Clear Market",
    ),
    "sentiment": AnalystSpec(
        key="sentiment",
        agent_node="Sentiment Analyst",
        tool_node="tools_sentiment",
        clear_node="Msg Clear Sentiment",
    ),
    "news": AnalystSpec(
        key="news",
        agent_node="News Analyst",
        tool_node="tools_news",
        clear_node="Msg Clear News",
    ),
    "fundamentals": AnalystSpec(
        key="fundamentals",
        agent_node="Fundamentals Analyst",
        tool_node="tools_fundamentals",
        clear_node="Msg Clear Fundamentals",
    ),
    # A 股特色分析师
    "northbound": AnalystSpec(
        key="northbound",
        agent_node="Northbound Analyst",
        tool_node="tools_northbound",
        clear_node="Msg Clear Northbound",
    ),
    "sector": AnalystSpec(
        key="sector",
        agent_node="Sector Analyst",
        tool_node="tools_sector",
        clear_node="Msg Clear Sector",
    ),
}


def build_analyst_execution_plan(
    selected_analysts: list[str],
    concurrency_limit: int = 1,
) -> AnalystExecutionPlan:
    """构建分析师执行计划

    Args:
        selected_analysts: 选择的分析师类型列表
        concurrency_limit: 并发限制 (1 = 串行, 0 = 无限)
    """
    plan = AnalystExecutionPlan()
    for key in selected_analysts:
        spec = ANALYST_REGISTRY.get(key)
        if spec:
            plan.specs.append(spec)
    return plan
