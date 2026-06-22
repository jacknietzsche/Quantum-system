"""状态传播器 — 参考 TradingAgents-CN 改进

关键改进:
1. 清晰的 HumanMessage 初始化 (确保所有 LLM 理解任务)
2. 工具调用计数器 (防死循环)
3. 支持进度回调的 stream mode
"""

from __future__ import annotations

from typing import Any


class Propagator:
    """创建初始状态和 graph 调用参数"""

    def __init__(self, max_recur_limit: int = 100):
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        stock_code: str,
        stock_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
        instrument_context: str = "",
    ) -> dict[str, Any]:
        """创建工作流初始状态

        改进: 创建明确的分析请求消息,确保所有 LLM (包括 DeepSeek) 都能理解任务.
        原始 TradingAgents 只传 ticker,某些 LLM 不理解.
        """
        from langchain_core.messages import HumanMessage

        # 构建清晰的分析请求
        display_name = stock_name if stock_name else stock_code
        analysis_request = (
            f"请对 {display_name} ({stock_code}) 进行全面的投资分析。"
            f"分析日期: {trade_date}。"
            f"请从技术面、情绪面、新闻面和基本面四个维度进行深度分析。"
        )

        if past_context:
            analysis_request += f"\n\n历史记忆参考:\n{past_context[:500]}"

        return {
            "messages": [HumanMessage(content=analysis_request)],
            # 基础信息
            "stock_code": stock_code,
            "stock_name": stock_name,
            "asset_type": asset_type,
            "trade_date": trade_date,
            "instrument_context": instrument_context,
            # 分析师报告
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "northbound_report": "",
            "sector_report": "",
            # 死循环修复: 工具调用计数器  # noqa: ERA001
            "market_tool_call_count": 0,
            "news_tool_call_count": 0,
            "sentiment_tool_call_count": 0,
            "fundamentals_tool_call_count": 0,
            "northbound_tool_call_count": 0,
            "sector_tool_call_count": 0,
            # 投资辩论
            "investment_debate_state": {
                "bull_history": "",
                "bear_history": "",
                "history": "",
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
            "investment_plan": "",
            # Master Council
            "master_council_report": "",
            "master_views": [],
            "skill_context": "",
            "master_weight_factor": 1.0,
            "master_position_factor": 1.0,
            # 交易员
            "trader_investment_plan": "",
            # 风控辩论
            "risk_debate_state": {
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "history": "",
                "latest_speaker": "",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "judge_decision": "",
                "count": 0,
            },
            # 最终决策
            "final_trade_decision": "",
            # 历史记忆
            "past_context": past_context,
            # 发送者
            "sender": "",
        }

    def get_graph_args(self, use_progress_callback: bool = False) -> dict[str, Any]:
        """获取 graph 调用参数

        Args:
            use_progress_callback: True 用 "updates" 模式 (节点级进度)
                                   False 用 "values" 模式 (完整状态)
        """
        stream_mode = "updates" if use_progress_callback else "values"
        return {
            "stream_mode": stream_mode,
            "config": {"recursion_limit": self.max_recur_limit},
        }
