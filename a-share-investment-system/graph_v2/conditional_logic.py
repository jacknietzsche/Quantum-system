"""条件路由逻辑 — 参考 TradingAgents-CN 改进

关键改进:
1. 死循环修复: 工具调用计数器 + 最大次数限制
2. 报告完成检查: 已有报告则跳过工具调用
3. 详细调试日志
"""

from agents_v2.agent_states import AgentState
from agents_v2.utils.logging_init import get_logger

logger = get_logger("agents")


class ConditionalLogic:
    """工作流条件路由 — 含死循环保护"""

    def __init__(self, max_debate_rounds: int = 1, max_risk_discuss_rounds: int = 1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        self.max_tool_calls = 3  # 每个分析师最大工具调用次数

    # ─── 内部辅助 ───

    def _should_continue_analyst(
        self,
        state: AgentState,
        analyst_key: str,
        report_key: str,
        clear_node: str,
        tool_node: str,
    ) -> str:
        """通用分析师工具调用路由逻辑

        死循环修复策略:
        1. 达到最大工具调用次数 → 强制结束
        2. 报告已完成 (>100 字) → 跳过工具调用
        3. 有 tool_calls → 执行工具
        4. 否则 → 结束
        """
        messages = state.get("messages", [])
        report = state.get(report_key, "")
        counter_key = f"{analyst_key}_tool_call_count"
        tool_call_count = state.get(counter_key, 0)

        logger.info(
            f"[{analyst_key}] 消息数={len(messages)} 报告长度={len(report)} 工具调用={tool_call_count}/{self.max_tool_calls}"
        )

        # 1. 死循环修复: 达到最大次数 → 强制结束
        if tool_call_count >= self.max_tool_calls:
            logger.warning(f"[{analyst_key}] 达到最大工具调用次数,强制结束")
            return clear_node

        # 2. 报告已完成 → 跳过
        if report and len(report) > 100:
            logger.info(f"[{analyst_key}] 报告已完成,跳过工具调用")
            return clear_node

        # 3. 有 tool_calls → 执行工具
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                logger.info(f"[{analyst_key}] 检测到 {len(last_msg.tool_calls)} 个工具调用")
                return tool_node

        # 4. 结束
        logger.info(f"[{analyst_key}] 无工具调用,结束")
        return clear_node

    # ─── 分析师工具调用路由 ───

    def should_continue_market(self, state: AgentState) -> str:
        return self._should_continue_analyst(
            state,
            "market",
            "market_report",
            "Msg Clear Market",
            "tools_market",
        )

    def should_continue_sentiment(self, state: AgentState) -> str:
        return self._should_continue_analyst(
            state,
            "sentiment",
            "sentiment_report",
            "Msg Clear Sentiment",
            "tools_sentiment",
        )

    def should_continue_news(self, state: AgentState) -> str:
        return self._should_continue_analyst(
            state,
            "news",
            "news_report",
            "Msg Clear News",
            "tools_news",
        )

    def should_continue_fundamentals(self, state: AgentState) -> str:
        return self._should_continue_analyst(
            state,
            "fundamentals",
            "fundamentals_report",
            "Msg Clear Fundamentals",
            "tools_fundamentals",
        )

    def should_continue_northbound(self, state: AgentState) -> str:
        return self._should_continue_analyst(
            state,
            "northbound",
            "northbound_report",
            "Msg Clear Northbound",
            "tools_northbound",
        )

    def should_continue_sector(self, state: AgentState) -> str:
        return self._should_continue_analyst(
            state,
            "sector",
            "sector_report",
            "Msg Clear Sector",
            "tools_sector",
        )

    # ─── 投资辩论路由 ───

    def should_continue_debate(self, state: AgentState) -> str:
        """牛/熊辩论: 达到轮次上限 → Research Manager, 否则轮流发言"""
        debate = state.get("investment_debate_state", {})
        count = debate.get("count", 0)
        max_count = 2 * self.max_debate_rounds
        current = debate.get("current_response", "")

        logger.info(f"[投资辩论] 轮次={count}/{max_count} 当前发言者={current[:20]}...")

        if count >= max_count:
            logger.info("[投资辩论] 达到上限,转交 Research Manager")
            return "Research Manager"

        if current.startswith(("Bull", "多")):
            return "Bear Researcher"
        return "Bull Researcher"

    # ─── 风控辩论路由 ───

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """三方风控辩论: 激进 → 保守 → 中性 → 循环"""
        risk = state.get("risk_debate_state", {})
        count = risk.get("count", 0)
        max_count = 3 * self.max_risk_discuss_rounds
        speaker = risk.get("latest_speaker", "")

        logger.info(f"[风控辩论] 轮次={count}/{max_count} 最后发言={speaker}")

        if count >= max_count:
            logger.info("[风控辩论] 达到上限,转交 Portfolio Manager")
            return "Portfolio Manager"

        if speaker.startswith(("Aggressive", "激进")):
            return "Conservative Analyst"
        if speaker.startswith(("Conservative", "保守")):
            return "Neutral Analyst"
        return "Aggressive Analyst"
