"""反思器增强 — 参考 TradingAgents-CN/reflection.py

关键改进:
1. 每个 Agent 单独反思 (牛/熊/交易员/研究经理/风控)
2. 结构化的反思 prompt
3. 记忆更新支持
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Reflector:
    """决策反思器 — 基于最终决策和实际结果生成反思"""

    # 反思 prompt 模板
    REFLECTION_PROMPT = """你是一位专业的投资复盘分析师.请基于以下信息生成反思:

股票: {stock_code}
日期: {trade_date}
角色: {role}
原始决策: {decision}
实际收益: {raw_return}
超额收益: {alpha_return}
持仓天数: {holding_days}天

请分析:
1. 决策的准确性
2. 哪些因素被正确/错误评估
3. 可以改进的地方

输出一段话(不超过200字),直接开始分析."""

    def __init__(self, llm: Any):
        self.llm = llm

    def generate_reflection(
        self,
        stock_code: str,
        trade_date: str,
        decision: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        role: str = "综合决策",
    ) -> str:
        """生成反思段落"""
        prompt = self.REFLECTION_PROMPT.format(
            stock_code=stock_code,
            trade_date=trade_date,
            role=role,
            decision=decision[:500],
            raw_return=f"{raw_return:+.1%}",
            alpha_return=f"{alpha_return:+.1%}",
            holding_days=holding_days,
        )

        try:
            response = self.llm.invoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning("[反思] 生成失败: %s", e)
            return f"收益{raw_return:+.1%}, 超额{alpha_return:+.1%}, 持仓{holding_days}天."

    def reflect_all_agents(
        self,
        stock_code: str,
        trade_date: str,
        state: dict[str, Any],
        raw_return: float,
        alpha_return: float,
        holding_days: int,
    ) -> dict[str, str]:
        """对所有 Agent 生成单独反思

        Returns:
            {
                "bull": "多方反思...",
                "bear": "空方反思...",
                "trader": "交易员反思...",
                "research_manager": "研究经理反思...",
                "risk_manager": "风控反思...",
                "portfolio_manager": "组合经理反思...",
            }
        """
        reflections = {}
        debate = state.get("investment_debate_state", {})
        risk = state.get("risk_debate_state", {})

        agent_decisions = {
            "bull": debate.get("bull_history", "")[:300],
            "bear": debate.get("bear_history", "")[:300],
            "trader": state.get("trader_investment_plan", "")[:300],
            "research_manager": debate.get("judge_decision", "")[:300],
            "risk_manager": risk.get("judge_decision", "")[:300],
            "portfolio_manager": state.get("final_trade_decision", "")[:300],
        }

        for role, decision in agent_decisions.items():
            if decision:
                try:
                    reflections[role] = self.generate_reflection(
                        stock_code=stock_code,
                        trade_date=trade_date,
                        decision=decision,
                        raw_return=raw_return,
                        alpha_return=alpha_return,
                        holding_days=holding_days,
                        role=role,
                    )
                except Exception as e:
                    logger.warning(f"[反思] {role} 反思失败: {e}")
                    reflections[role] = f"{role}: 收益{raw_return:+.1%}"

        return reflections

    def generate_summary_reflection(self, reflections: dict[str, str]) -> str:
        """汇总所有 Agent 的反思为一段总结"""
        if not reflections:
            return ""

        parts = []
        for role, reflection in reflections.items():
            if reflection:
                parts.append(f"[{role}] {reflection[:100]}")

        return "\n".join(parts)
