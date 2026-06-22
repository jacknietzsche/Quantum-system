"""主工作流定义。

设计依据: S06 §6.1, experiments exp4.1-exp4.3/exp7.1。
LangGraph StateGraph: 分析师→辩论→研究经理→交易员→风险→组合经理。
"""

from __future__ import annotations

import logging

from core.llm_client import LLMClient
from core.state import AgentState
from graph.conditional_logic import (
    route_after_pm,
    should_continue_investment_debate,
    should_continue_risk_debate,
)

logger = logging.getLogger(__name__)


def build_trading_graph(llm_client: LLMClient, checkpointer=None):
    """
    构建主工作流图。
    返回编译后的图对象。

    Args:
        llm_client: LLM客户端
        checkpointer: LangGraph checkpointer实例，用于状态持久化。
                      默认使用InMemorySaver（进程内持久化，支持断点恢复+中间状态检查）。
                      传入None则不使用checkpointer。
    """
    from langgraph.graph import END, START, StateGraph

    # 默认使用内存checkpointer，支持断点恢复和中间状态检查
    if checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver

        checkpointer = InMemorySaver()

    from agents.analysts.fundamentals_analyst import create_fundamentals_analyst

    # 导入Agent创建函数
    from agents.analysts.market_analyst import create_market_analyst
    from agents.analysts.news_analyst import create_news_analyst
    from agents.analysts.sentiment_analyst import create_sentiment_analyst
    from agents.masters.review import create_master_review, create_master_selector
    from agents.researchers.bear_researcher import create_bear_researcher
    from agents.researchers.bull_researcher import create_bull_researcher
    from agents.researchers.research_manager import create_research_manager
    from agents.risk_mgmt.aggressive_analyst import create_aggressive_analyst
    from agents.risk_mgmt.conservative_analyst import create_conservative_analyst
    from agents.risk_mgmt.neutral_analyst import create_neutral_analyst
    from agents.risk_mgmt.portfolio_manager import create_portfolio_manager
    from agents.trader.trader import create_trader

    graph = StateGraph(AgentState)

    # === 分析师团队 ===
    graph.add_node("market_analyst", create_market_analyst(llm_client))
    graph.add_node("fundamentals_analyst", create_fundamentals_analyst(llm_client))
    graph.add_node("news_analyst", create_news_analyst(llm_client))
    graph.add_node("sentiment_analyst", create_sentiment_analyst(llm_client))

    # 分析师并行（通过条件边分发）
    graph.add_edge(START, "market_analyst")
    graph.add_edge("market_analyst", "fundamentals_analyst")
    graph.add_edge("fundamentals_analyst", "news_analyst")
    graph.add_edge("news_analyst", "sentiment_analyst")

    # === 多空辩论 ===
    graph.add_node("bull_researcher", create_bull_researcher(llm_client))
    graph.add_node("bear_researcher", create_bear_researcher(llm_client))

    graph.add_edge("sentiment_analyst", "bull_researcher")
    graph.add_conditional_edges(
        "bull_researcher",
        should_continue_investment_debate,
        {"continue": "bear_researcher", "end": "research_manager"},
    )
    graph.add_conditional_edges(
        "bear_researcher",
        should_continue_investment_debate,
        {"continue": "bull_researcher", "end": "research_manager"},
    )

    # === 研究经理 → 交易员 ===
    graph.add_node("research_manager", create_research_manager(llm_client))
    graph.add_node("trader", create_trader(llm_client))
    graph.add_edge("research_manager", "trader")

    # === 风险辩论 ===
    graph.add_node("aggressive_analyst", create_aggressive_analyst(llm_client))
    graph.add_node("conservative_analyst", create_conservative_analyst(llm_client))
    graph.add_node("neutral_analyst", create_neutral_analyst(llm_client))

    graph.add_edge("trader", "aggressive_analyst")
    graph.add_conditional_edges(
        "aggressive_analyst",
        should_continue_risk_debate,
        {"continue": "conservative_analyst", "end": "portfolio_manager"},
    )
    graph.add_conditional_edges(
        "conservative_analyst",
        should_continue_risk_debate,
        {"continue": "neutral_analyst", "end": "portfolio_manager"},
    )
    graph.add_conditional_edges(
        "neutral_analyst",
        should_continue_risk_debate,
        {"continue": "aggressive_analyst", "end": "portfolio_manager"},
    )

    # === 组合经理 → 大师评审（条件）/ END ===
    graph.add_node("portfolio_manager", create_portfolio_manager(llm_client))

    # 大师选择器 + 大师评审
    graph.add_node("master_selector", create_master_selector(llm_client))  # type: ignore[call-overload]
    graph.add_node("master_review", create_master_review(llm_client))  # type: ignore[call-overload]

    # 组合经理后，根据enable_masters决定是否进入大师评审
    graph.add_conditional_edges(
        "portfolio_manager",
        route_after_pm,
        {"with_masters": "master_selector", "final": END},
    )

    # 大师选择 → 大师评审 → END
    graph.add_edge("master_selector", "master_review")
    graph.add_edge("master_review", END)

    return graph.compile(checkpointer=checkpointer)
