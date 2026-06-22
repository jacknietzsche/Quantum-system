"""IntegratorAgent - 整合员: 按规则计算 llm_adjustment"""

import logging

logger = logging.getLogger(__name__)


class IntegratorAgent:
    """整合三个审计结果, 计算最终 llm_adjustment"""

    def integrate(
        self,
        quant_report: dict,
        financial_report: dict,
        market_report: dict,
        master_report: dict,
        max_adjustment: int = 15,
        force_dissent: bool = False,
    ) -> dict:
        """按规则计算 llm_adjustment"""
        base = 0

        # 财务排雷
        risk_flags = financial_report.get("risk_flags", [])
        if risk_flags:
            base -= len(risk_flags) * 3

        # 市场确认
        tech_score = market_report.get("tech_confirmation_score", 50)
        if tech_score >= 70:
            base += 5
        elif tech_score <= 30:
            base -= 5

        # 大师适配
        endorsement = master_report.get("endorsement_strength", 0)
        if endorsement >= 0.8:
            base += 5

        # 约束检查
        final = max(-max_adjustment, min(max_adjustment, base))
        needs_dissent = force_dissent and abs(final) >= 15

        return {
            "llm_adjustment": final,
            "needs_dissent_review": needs_dissent,
            "breakdown": {
                "financial_penalty": -len(risk_flags) * 3 if risk_flags else 0,
                "market_confirmation": 5 if tech_score >= 70 else (-5 if tech_score <= 30 else 0),
                "master_endorsement": 5 if endorsement >= 0.8 else 0,
            },
        }
