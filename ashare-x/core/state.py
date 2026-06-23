"""AgentState — LangGraph 工作流的全局状态 (见 S06, experiments exp7.1)。

设计依据: IMPLEMENTATION_PLAN.md §1.4, S04 数据契约。
LangGraph 要求 state 是可被节点返回值 merge 的 dict; 用 TypedDict 标注字段类型供 IDE/mypy。

字段分组:
- 输入: ticker, stocks, mode
- 数据: market_data, fundamentals, news, sentiment (各 Agent 写入)
- 分析师产出: analyst_signals (dict[agent_name -> AnalystSignal])
- 辩论: debate_messages (多空/风险辩论的完整消息历史)
- 决策: research_decision, trade_proposal, final_decision
- 元: messages (LLM 原始消息), errors, budget (BudgetState 快照)

注意: 这里只定义结构, 不含业务逻辑。Pydantic schema (AnalystSignal 等) 在 agents 层定义
(Phase 3), 此处用 TypedDict + Any 保持 Phase 1 独立可测。
"""

from __future__ import annotations

from typing import Any, TypedDict


class AnalystSignal(TypedDict, total=False):
    """单个分析师的输出 (完整 schema 在 Phase 3 用 Pydantic 固化)。"""

    signal: str  # bullish / bearish / neutral
    confidence: float  # 0-100
    reasoning: str
    agent: str


class AgentState(TypedDict, total=False):
    """LangGraph 全局状态。total=False: 节点按需写入字段, 无需预填全部。"""

    # ── 输入 ──
    ticker: str  # 当前分析的股票代码 (标准化后, 如 "600519")
    stocks: list[str]  # 批量分析时的股票列表
    mode: str  # "full" / "fast" (见 budget policy)
    config: dict[str, Any]  # 运行期配置（debate轮次、功能开关等）

    # ── 数据层产出 (tools/ 写入) ──
    market_data: dict[str, Any]  # K线 + 技术指标
    fundamentals: dict[str, Any]  # 财报数据
    news: list[dict[str, Any]]
    sentiment: dict[str, Any]  # 龙虎榜/北向/融资融券

    # ── 分析师产出 ──
    analyst_signals: dict[str, AnalystSignal]

    # ── Agent 报告（自由文本，供后续节点/前端展示） ──
    market_analyst_report: str
    fundamentals_analyst_report: str
    news_analyst_report: str
    sentiment_analyst_report: str
    bull_researcher_report: str
    bear_researcher_report: str
    research_manager_report: str
    trader_report: str
    aggressive_analyst_report: str
    conservative_analyst_report: str
    neutral_analyst_report: str
    portfolio_manager_report: str
    master_review_report: str

    # ── 辩论 ──
    debate_messages: list[dict[str, Any]]  # 多空 + 风险辩论消息历史
    investment_debate_rounds: int  # 多空辩论已完成轮次
    risk_debate_rounds: int  # 风险辩论已完成轮次

    # ── 决策 ──
    research_decision: dict[str, Any]  # 研究经理裁决
    trade_proposal: dict[str, Any]  # 交易员提案
    final_decision: dict[str, Any]  # 组合经理最终决策

    # ── 大师Agent ──
    selected_masters: list[str]  # master_selector选中的大师
    master_signals: dict[str, AnalystSignal]  # 大师Agent输出信号
    master_prior_context: str  # 大师评审前注入的前序摘要

    # ── 元 ──
    messages: list[dict[str, Any]]  # LLM 原始消息 (可压缩, 见 S04:24)
    errors: list[dict[str, Any]]  # 节点级错误记录
    budget_snapshot: dict[str, Any]  # BudgetState 快照 (used_rmb 等)


def make_initial_state(ticker: str | None = None, **kwargs: Any) -> AgentState:
    """创建初始 state (空容器 + 可选 ticker)。便于测试与节点启动。"""
    state: AgentState = {
        "analyst_signals": {},
        "debate_messages": [],
        "investment_debate_rounds": 0,
        "risk_debate_rounds": 0,
        "messages": [],
        "errors": [],
        "mode": "full",
    }
    if ticker:
        state["ticker"] = ticker
    state.update(kwargs)  # type: ignore[typeddict-item]
    return state
