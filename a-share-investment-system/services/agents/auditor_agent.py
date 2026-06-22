"""AuditorAgent - 审计员: 抽检关键 claim 是否被 source_data 支持"""

import logging

logger = logging.getLogger(__name__)


class AuditorAgent:
    """审计员 - 验证整合结果中的关键数据引用是否真实"""

    def audit(self, integrator_result: dict, source_data: dict) -> dict:
        """抽检关键 claim, 防止 AI 虚构引用"""
        audit_chain = []
        all_passed = True

        adjustment = integrator_result.get("llm_adjustment", 0)
        breakdown = integrator_result.get("breakdown", {})

        # 检查 adjustment 是否在合理范围内
        if abs(adjustment) > 20:
            audit_chain.append(
                {
                    "check": "adjustment_range",
                    "passed": False,
                    "detail": f"调整值{adjustment}超出±20范围",
                }
            )
            all_passed = False
        else:
            audit_chain.append({"check": "adjustment_range", "passed": True})

        # 检查财务 penalty 是否有对应的 risk_flags
        financial_penalty = breakdown.get("financial_penalty", 0)
        if financial_penalty < 0:
            risk_flags = source_data.get("risk_flags", [])
            expected_penalty = -len(risk_flags) * 3
            if financial_penalty != expected_penalty:
                audit_chain.append(
                    {
                        "check": "financial_penalty_consistency",
                        "passed": False,
                        "detail": (
                            f"财务罚分{financial_penalty}与risk_flags({len(risk_flags)}项)不匹配"
                        ),
                    }
                )
                all_passed = False
            else:
                audit_chain.append({"check": "financial_penalty_consistency", "passed": True})

        # 检查 master endorsement
        master_endorsement = breakdown.get("master_endorsement", 0)
        if master_endorsement > 0:
            master_details = source_data.get("master_details", [])
            if not master_details:
                audit_chain.append(
                    {
                        "check": "master_endorsement_has_support",
                        "passed": False,
                        "detail": "大师加分但master_details为空",
                    }
                )
                all_passed = False
            else:
                audit_chain.append({"check": "master_endorsement_has_support", "passed": True})

        return {
            "auditor_passed": all_passed,
            "audit_chain": audit_chain,
        }
