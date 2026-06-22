"""工作流图构建 — 参考 TradingAgents/graph/setup.py

组装所有 Agent 节点,定义边和条件路由.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents_v2.agent_states import AgentState
from agents_v2.analysts import (
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_news_analyst,
    create_northbound_analyst,
    create_sector_analyst,
    create_sentiment_analyst,
)
from agents_v2.managers import create_portfolio_manager
from agents_v2.researchers import (
    create_bear_researcher,
    create_bull_researcher,
    create_research_manager,
)
from agents_v2.risk_mgmt import (
    create_aggressive_debator,
    create_conservative_debator,
    create_neutral_debator,
)
from agents_v2.trader import create_trader
from graph_v2.analyst_execution import build_analyst_execution_plan
from graph_v2.conditional_logic import ConditionalLogic
from graph_v2.master_council import create_master_council_node


class GraphSetup:
    """工作流图构建器

    职责:
    1. 注册所有 Agent 节点
    2. 定义节点间连接 (边)
    3. 定义条件路由
    """

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
    ):
        self.quick_llm = quick_thinking_llm
        self.deep_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.concurrency_limit = analyst_concurrency_limit

    def setup_graph(
        self,
        selected_analysts: list[str] | None = None,
    ) -> StateGraph:
        """构建完整工作流图

        Args:
            selected_analysts: 启用的分析师列表
                可选: market, sentiment, news, fundamentals, northbound, sector
        """
        if selected_analysts is None:
            selected_analysts = ["market", "sentiment", "news", "fundamentals"]

        plan = build_analyst_execution_plan(
            selected_analysts,
            concurrency_limit=self.concurrency_limit,
        )

        # ─── 分析师工厂映射 ───
        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_llm),
            "sentiment": lambda: create_sentiment_analyst(self.quick_llm),
            "news": lambda: create_news_analyst(self.quick_llm),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_llm),
            "northbound": lambda: create_northbound_analyst(self.quick_llm),
            "sector": lambda: create_sector_analyst(self.quick_llm),
        }

        # ─── 创建节点 ───
        workflow = StateGraph(AgentState)

        # 分析师节点
        for spec in plan.specs:
            factory = analyst_factories.get(spec.key)
            if factory:
                workflow.add_node(spec.agent_node, factory())
            workflow.add_node(spec.clear_node, create_msg_delete())
            tool_key = spec.key
            if tool_key in self.tool_nodes:
                workflow.add_node(spec.tool_node, self.tool_nodes[tool_key])

        # 研究员节点
        master_council_node = create_master_council_node()
        bull_node = create_bull_researcher(self.quick_llm)
        bear_node = create_bear_researcher(self.quick_llm)
        research_manager_node = create_research_manager(self.deep_llm)

        # 交易员节点
        trader_node = create_trader(self.quick_llm)

        # 风控节点
        aggressive_node = create_aggressive_debator(self.quick_llm)
        conservative_node = create_conservative_debator(self.quick_llm)
        neutral_node = create_neutral_debator(self.quick_llm)

        # 组合经理节点
        pm_node = create_portfolio_manager(self.deep_llm)

        # 注册节点
        workflow.add_node("Master Council", master_council_node)
        workflow.add_node("Bull Researcher", bull_node)
        workflow.add_node("Bear Researcher", bear_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_node)
        workflow.add_node("Conservative Analyst", conservative_node)
        workflow.add_node("Neutral Analyst", neutral_node)
        workflow.add_node("Portfolio Manager", pm_node)

        # ─── 定义边 ───

        # 入口: 第一个分析师  # noqa: ERA001
        workflow.add_edge(START, plan.specs[0].agent_node)

        # 分析师串联: analyst1 → tools → clear → analyst2 → ...
        for i, spec in enumerate(plan.specs):
            current_analyst = spec.agent_node
            current_tools = spec.tool_node
            current_clear = spec.clear_node

            # 条件边: analyst → tools 或 clear
            if spec.key in self.tool_nodes:
                workflow.add_conditional_edges(
                    current_analyst,
                    getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                    [current_tools, current_clear],
                )
                workflow.add_edge(current_tools, current_analyst)
            else:
                # 无工具: 直接到 clear
                workflow.add_edge(current_analyst, current_clear)

            # 连接到下一个分析师或 Bull Researcher
            if i < len(plan.specs) - 1:
                workflow.add_edge(current_clear, plan.specs[i + 1].agent_node)
            else:
                workflow.add_edge(current_clear, "Master Council")

        # Master Council 在研究员辩论前沉淀大师与技能观点
        workflow.add_edge("Master Council", "Bull Researcher")

        # 研究员辩论: Bull ↔ Bear, 达到上限 → Research Manager
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )

        # Research Manager → Trader
        workflow.add_edge("Research Manager", "Trader")

        # Trader → 风控三方辩论
        workflow.add_edge("Trader", "Aggressive Analyst")

        # 风控辩论: 激进 → 保守 → 中性 → 循环, 达到上限 → PM
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )

        # Portfolio Manager → END
        workflow.add_edge("Portfolio Manager", END)

        return workflow
