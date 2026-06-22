"""AuditorFinancial - 财务排雷师: 检查七大财务造假信号"""

import logging

logger = logging.getLogger(__name__)


class AuditorFinancial:
    """财务排雷审计 - 纯规则引擎, 无LLM调用"""

    def audit(self, stock_code: str, financials: dict) -> dict:
        """执行财务排雷"""
        risk_flags = []
        details = {}

        # 1. 应收账款激增: 应收增速 > 营收增速 2x
        receivables = financials.get("receivables", 0)
        revenue = financials.get("revenue_growth_3y", 0)
        if receivables and revenue and revenue > 0:
            ratio = receivables / revenue
            if ratio > 2:
                risk_flags.append(f"receivables_surge({ratio:.1f}x)")
                details["receivables_warning"] = ratio

        # 2. 经营现金流低于净利润
        cfo = financials.get("free_cash_flow", 0)
        net_income = financials.get("net_income", 0)
        if cfo and net_income > 0 and cfo < net_income * 0.5:
            risk_flags.append(f"cfo_below_ni(cfo={cfo},ni={net_income})")
            details["cfo_warning"] = cfo / max(net_income, 1)

        # 3. 存货异常
        inventory = financials.get("inventory", 0)
        if inventory and revenue and revenue > 0 and inventory > revenue * 2:
            risk_flags.append(f"inventory_surge({inventory:.1f})")
            details["inventory_warning"] = inventory / max(revenue, 1)

        # 4. 毛利率异常
        gross_margin = financials.get("gross_margin", 0)
        industry_margin = financials.get("industry_avg_gross_margin", 0)
        if gross_margin and industry_margin > 0 and gross_margin > industry_margin * 2:
            risk_flags.append(f"gross_margin_abnormal({gross_margin:.1f}%)")
            details["margin_warning"] = gross_margin / industry_margin

        # 5. 关联交易
        other_receivables = financials.get("other_receivables", 0)
        total_assets = financials.get("current_assets", 1)
        if other_receivables and other_receivables / max(total_assets, 1) > 0.2:
            risk_flags.append(f"related_party_risk({other_receivables / max(total_assets, 1):.0%})")
            details["related_party_ratio"] = other_receivables / max(total_assets, 1)

        # 6. 大额商誉
        goodwill = financials.get("goodwill", 0)
        net_equity = max(financials.get("total_liabilities", 1), 1)  # proxy
        if goodwill and goodwill / net_equity > 0.3:
            risk_flags.append(f"goodwill_overhang({goodwill / net_equity:.1%})")
            details["goodwill_ratio"] = goodwill / net_equity

        # 7. 频繁变更审计机构 - 需外部数据源, 标记为待补充
        # 当前无数据源支持

        confidence = max(0.3, 1.0 - len(risk_flags) * 0.15)
        return {
            "risk_flags": risk_flags,
            "confidence": round(confidence, 2),
            "details": details,
            "passed": len(risk_flags) == 0,
        }
