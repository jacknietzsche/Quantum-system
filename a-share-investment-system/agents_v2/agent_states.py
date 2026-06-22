"""Agent 状态定义 — 参考 TradingAgents-CN + TradingAgents

A 股适配的状态模型,支持:
- 分析师报告 (市场/情绪/新闻/基本面)
- 投资辩论 (牛/熊)
- 风控辩论 (激进/保守/中性)
- 完整决策链
- 工具调用计数器 (防死循环)
"""

from typing import Annotated, Any

from typing_extensions import TypedDict


class InvestDebateState(TypedDict):
    """投资辩论状态 — 牛/熊研究员来回讨论"""

    bull_history: Annotated[str, "多方论点历史"]
    bear_history: Annotated[str, "空方论点历史"]
    history: Annotated[str, "完整辩论历史"]
    current_response: Annotated[str, "最新回应"]
    judge_decision: Annotated[str, "裁判最终裁决"]
    count: Annotated[int, "辩论轮次计数"]


class RiskDebateState(TypedDict):
    """风控辩论状态 — 激进/保守/中性三方讨论"""

    aggressive_history: Annotated[str, "激进方论点"]
    conservative_history: Annotated[str, "保守方论点"]
    neutral_history: Annotated[str, "中立方论点"]
    history: Annotated[str, "完整风控辩论历史"]
    latest_speaker: Annotated[str, "最后发言方"]
    current_aggressive_response: Annotated[str, "激进方最新回应"]
    current_conservative_response: Annotated[str, "保守方最新回应"]
    current_neutral_response: Annotated[str, "中立方最新回应"]
    judge_decision: Annotated[str, "风控裁判决定"]
    count: Annotated[int, "风控辩论轮次"]


class AgentState(TypedDict):
    """完整 Agent 状态 — 工作流全局上下文"""

    # ─── 基础信息 ───
    stock_code: Annotated[str, "股票代码 (6位)"]
    stock_name: Annotated[str, "股票名称"]
    asset_type: Annotated[str, "资产类型: stock / fund / index"]
    trade_date: Annotated[str, "分析日期"]
    instrument_context: Annotated[str, "确定性解析的标的身份信息"]

    # ─── 分析师报告 (并行产出) ───
    market_report: Annotated[str, "技术分析报告"]
    sentiment_report: Annotated[str, "情绪分析报告"]
    news_report: Annotated[str, "新闻分析报告"]
    fundamentals_report: Annotated[str, "基本面分析报告"]

    # ─── A 股特色报告 ───
    northbound_report: Annotated[str, "北向资金报告"]
    sector_report: Annotated[str, "板块轮动报告"]

    # ─── 死循环修复: 工具调用计数器 ───
    market_tool_call_count: Annotated[int, "市场分析师工具调用次数"]
    news_tool_call_count: Annotated[int, "新闻分析师工具调用次数"]
    sentiment_tool_call_count: Annotated[int, "情绪分析师工具调用次数"]
    fundamentals_tool_call_count: Annotated[int, "基本面分析师工具调用次数"]
    northbound_tool_call_count: Annotated[int, "北向资金分析师工具调用次数"]
    sector_tool_call_count: Annotated[int, "板块分析师工具调用次数"]

    # ─── Master Council ───
    master_council_report: Annotated[str, "Master Agent / 投资大师综合报告"]
    master_views: Annotated[list[Any], "结构化 Master Agent 视图"]
    skill_context: Annotated[str, "注入到主链路的技能知识摘要"]
    master_weight_factor: Annotated[float, "Master Council 对评分/置信度的加权因子"]
    master_position_factor: Annotated[float, "Master Council 对仓位的调整因子"]

    # ─── 研究员辩论 ───
    investment_debate_state: Annotated[InvestDebateState, "投资辩论状态"]
    investment_plan: Annotated[str, "研究经理的投资计划"]

    # ─── 交易员 ───
    trader_investment_plan: Annotated[str, "交易员的投资方案"]

    # ─── 风控辩论 ───
    risk_debate_state: Annotated[RiskDebateState, "风控辩论状态"]

    # ─── 最终决策 ───
    final_trade_decision: Annotated[str, "最终交易决策"]

    # ─── 历史记忆 ───
    past_context: Annotated[str, "记忆系统注入的历史上下文"]

    # ─── 消息流 (LangGraph MessagesState 兼容) ───
    messages: Annotated[list[Any], "Agent 消息历史"]
    sender: Annotated[str, "发送消息的 Agent"]
