"""AuditorMaster - 大师适配分析师: 判断股票最匹配哪几位大师"""

import logging

logger = logging.getLogger(__name__)


class AuditorMaster:
    """大师适配分析 - 基于 quant_report 的因子分寻找匹配"""

    def audit(
        self, stock_code: str, quant_report: dict, master_opinions: dict | None = None
    ) -> dict:
        """执行大师适配分析"""
        if not master_opinions:
            return {
                "best_match": "unknown",
                "endorsement_strength": 0.0,
                "matching_factors": [],
                "confidence": 0.0,
            }

        best_match = ""
        best_score = 0
        matching_factors = []

        for analyst, opinion in master_opinions.items():
            analyst_score = opinion.get("score", 0)
            if analyst_score > best_score:
                best_score = analyst_score
                best_match = analyst

        roe_level = quant_report.get("roe_level", "")
        pe_level = quant_report.get("pe_level", "")

        if "high" in roe_level:
            matching_factors.append("high_roe")
        if pe_level == "low":
            matching_factors.append("low_pe")
        if best_score >= 80:
            matching_factors.append("strong_consensus")

        endorsement = min(1.0, best_score / 100.0)
        return {
            "best_match": best_match,
            "endorsement_strength": round(endorsement, 2),
            "matching_factors": matching_factors,
            "confidence": 0.7,
        }
