"""19位投资大师纯Python量化子分析 - 来源: ai-hedge-fund"""

import math

from shared.logging import emit_log


class QuantAnalyzers:
    """纯Python量化分析函数库,无需LLM调用"""

    def analyze_all(self, stock_code: str, financials: dict, prices: list[float]) -> list[dict]:
        """对所有持仓/目标股票运行全部分析师"""
        results = []
        for method in [
            self.buffett_analyze,
            self.graham_analyze,
            self.lynch_analyze,
            self.taleb_analyze,
            self.munger_analyze,
            self.pabrai_analyze,
        ]:
            try:
                result = method(stock_code, financials)
                results.append(result)
            except Exception as e:
                emit_log("WARNING", "quant", f"{type(e).__name__}: {str(e)[:100]}")
        return results

    def buffett_analyze(self, stock_code: str, f: dict) -> dict:
        """巴菲特框架:ROE + 安全边际 + 护城河评分"""
        roe = f.get("roe", 0)
        debt_equity = f.get("debt_to_equity", 100)
        gross_margin = f.get("gross_margin", 0)
        eps = f.get("eps", 0)
        bvps = f.get("bvps", 0)
        price = f.get("price", 1)

        roe_score = min(40, max(0, (roe - 10) * 4))
        gn_raw = 22.5 * max(eps, 0.01) * max(bvps, 0.01)
        graham_number = math.sqrt(gn_raw) if eps > 0 and bvps > 0 else 0
        safety_margin = (graham_number - price) / graham_number * 100 if graham_number > 0 else 0
        margin_score = min(30, max(0, safety_margin + 50))

        moat_score = 0
        if gross_margin > 40:
            moat_score += 10
        if debt_equity < 50:
            moat_score += 10
        if roe > 15:
            moat_score += 10

        total = roe_score + margin_score + moat_score
        return {
            "analyst": "buffett",
            "stock_code": stock_code,
            "score": min(100, total),
            "signal": "bullish" if total >= 60 else "bearish" if total < 30 else "neutral",
            "details": {
                "roe": roe,
                "roe_score": roe_score,
                "graham_number": round(graham_number, 2),
                "safety_margin_pct": round(safety_margin, 1),
                "margin_score": margin_score,
                "moat_score": moat_score,
            },
        }

    def graham_analyze(self, stock_code: str, f: dict) -> dict:
        """格雷厄姆框架:净流动资产 + 防御型标准 (字段缺失时降级为PE-only评分)"""
        current_assets = f.get("current_assets", 0)
        total_liabilities = f.get("total_liabilities", 0)
        shares = f.get("shares_outstanding", 0)
        price = f.get("price", 1)
        pe = f.get("pe_ratio", 0)

        has_ncav = current_assets > 0 and total_liabilities > 0 and shares > 0
        score = 0

        if has_ncav:
            ncav = (current_assets - total_liabilities) / shares
            ncav_discount = (ncav - price) / price * 100 if price > 0 else 0
            if ncav > price * 0.67:
                score += 50
            elif ncav > 0:
                score += 20
        else:
            ncav = 0
            ncav_discount = 0

        pe_ok = 0 < pe < 15
        if pe_ok:
            score += 30
        elif 0 < pe < 25:
            score += 15

        # PB 估值补充 (当 NCAV 数据缺失时)
        pb = f.get("pb_ratio", 0)
        if not has_ncav and 0 < pb < 1.5:
            score += 20
        elif not has_ncav and 0 < pb < 3:
            score += 10

        # When NCAV data is missing and score is low, give neutral base (40)
        if not has_ncav and score < 30:
            score = max(score, 40)

        return {
            "analyst": "graham",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 60 else "bearish" if score < 30 else "neutral",
            "details": {
                "ncav_per_share": round(ncav, 2),
                "ncav_discount_pct": round(ncav_discount, 1),
                "pe_ok": pe_ok,
                "has_ncav_data": has_ncav,
            },
        }

    def lynch_analyze(self, stock_code: str, f: dict) -> dict:
        """彼得·林奇框架:PEG + 业务简单性"""
        pe = f.get("pe_ratio", 100)
        earnings_growth = f.get("earnings_growth_3y", 5)
        peg = pe / max(earnings_growth, 0.1)

        score = 0
        if peg < 0.5:
            score += 50
        elif peg < 1.0:
            score += 35
        elif peg < 1.5:
            score += 20

        if earnings_growth > 15:
            score += 25
        elif earnings_growth > 10:
            score += 15
        elif earnings_growth > 0:
            score += 8

        # PE-based fallback when growth data is unreliable
        if score < 20 and 0 < pe < 30:
            score = max(score, 30)
        if score < 20 and 0 < pe < 50:
            score = max(score, 20)

        return {
            "analyst": "lynch",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 50 else "neutral",
            "details": {"peg": round(peg, 2), "earnings_growth_3y": earnings_growth, "pe": pe},
        }

    def taleb_analyze(self, stock_code: str, f: dict) -> dict:
        """塔勒布框架:反脆弱性 + 尾部风险"""
        debt_equity = f.get("debt_to_equity", 0)
        cash_ratio = f.get("cash_ratio", f.get("cash_to_assets", 0))
        # Fallback: use current_ratio as proxy when cash_ratio is missing
        if cash_ratio == 0:
            current_ratio = f.get("current_ratio", 0)
            if current_ratio > 0:
                cash_ratio = min(current_ratio * 10, 50)  # rough estimate

        anti_fragile = 0
        if debt_equity < 30:
            anti_fragile += 35
        elif debt_equity < 60:
            anti_fragile += 20
        if cash_ratio > 20:
            anti_fragile += 35
        elif cash_ratio > 10:
            anti_fragile += 20
        if f.get("gross_margin", 0) > 40:
            anti_fragile += 30

        return {
            "analyst": "taleb",
            "stock_code": stock_code,
            "score": min(100, anti_fragile),
            "signal": "bullish"
            if anti_fragile >= 60
            else "bearish"
            if anti_fragile < 30
            else "neutral",
            "details": {
                "debt_equity": debt_equity,
                "cash_to_assets": cash_ratio,
                "anti_fragile_score": anti_fragile,
            },
        }

    def munger_analyze(self, stock_code: str, f: dict) -> dict:
        """芒格框架:ROIC稳定性 + 管理层质量代理"""
        roe = f.get("roe", 0)
        roe_stability = f.get("roe_stability_5y", 5)
        insider_holding = f.get("insider_holding_pct", 0)

        score = 0
        if roe > 15:
            score += 35
        elif roe > 10:
            score += 20
        if roe_stability < 3:
            score += 30
        if insider_holding > 5:
            score += 20
        elif insider_holding > 1:
            score += 10

        return {
            "analyst": "munger",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 55 else "neutral",
            "details": {
                "roe": roe,
                "roe_stability_5y": roe_stability,
                "insider_holding_pct": insider_holding,
            },
        }

    def pabrai_analyze(self, stock_code: str, f: dict) -> dict:
        """帕布莱框架:低风险高回报不对称机会"""
        price = f.get("price", 1)
        book_value = f.get("bvps", 1)
        roe = f.get("roe", 0)

        pb = price / max(book_value, 0.01)
        score = 0
        if pb < 1.0:
            score += 40
        elif pb < 1.5:
            score += 25
        if roe > 15:
            score += 35
        elif roe > 10:
            score += 20

        return {
            "analyst": "pabrai",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 55 else "neutral",
            "details": {"pb": round(pb, 2), "roe": roe},
        }

    # ════════════════════════════════════════════
    #  增强版巴菲特深度分析(来源: ai-hedge-fund)
    # ════════════════════════════════════════════

    def buffett_deep_analyze(
        self, stock_code: str, f: dict, historical: list[dict] | None = None
    ) -> dict:
        """巴菲特完整框架:7项子分析 + 所有者收益 + 三阶段DCF"""
        analyses = {
            "fundamentals": self._buffett_fundamentals(f),
            "consistency": self._buffett_consistency(historical or [f]),
            "moat": self._buffett_moat(historical or [f]),
            "pricing_power": self._buffett_pricing_power(historical or [f]),
            "book_value": self._buffett_book_value_growth(historical or [f]),
            "management": self._buffett_management(f),
            "owner_earnings": self._buffett_owner_earnings(f, historical),
            "intrinsic_value": self._buffett_intrinsic_value(f, historical),
        }

        # 综合评分
        scores = [
            analyses["fundamentals"]["score"],
            analyses["consistency"]["score"],
            analyses["moat"]["score"],
            analyses["pricing_power"]["score"],
            analyses["book_value"]["score"],
            analyses["management"]["score"],
        ]
        total = sum(scores)
        max_score = sum(
            a.get("max_score", 5)
            for a in [
                analyses["fundamentals"],
                analyses["consistency"],
                analyses["moat"],
                analyses["pricing_power"],
                analyses["book_value"],
                analyses["management"],
            ]
        )
        normalized = min(100, int(total / max_score * 100)) if max_score > 0 else 50

        # 安全边际
        iv = analyses["intrinsic_value"].get("intrinsic_value")
        price = f.get("price", 1)
        margin = (iv - price) / price if iv and iv > 0 else None

        return {
            "analyst": "buffett_deep",
            "stock_code": stock_code,
            "score": normalized,
            "signal": "bullish"
            if normalized >= 60 and (margin is None or margin > 0)
            else "bearish"
            if normalized < 30
            else "neutral",
            "details": {
                "sub_scores": {k: v.get("score", 0) for k, v in analyses.items() if "score" in v},
                "owner_earnings": analyses["owner_earnings"].get("owner_earnings"),
                "intrinsic_value": iv,
                "market_price": price,
                "margin_of_safety_pct": round(margin * 100, 1) if margin is not None else None,
                "analysis_details": {k: v.get("details", "") for k, v in analyses.items()},
            },
        }

    def _buffett_fundamentals(self, f: dict) -> dict:
        """基本面分析:ROE/负债/利润率/流动性"""
        roe = f.get("roe", 0)
        debt_equity = f.get("debt_to_equity", 100)
        op_margin = f.get("operating_margin", f.get("gross_margin", 0))
        current_ratio = f.get("current_ratio", 1)

        score = 0
        reasons = []

        if roe > 0.15:
            score += 3
            reasons.append(f"优秀ROE: {roe:.1%}")
        elif roe > 0.10:
            score += 1
            reasons.append(f"一般ROE: {roe:.1%}")

        if debt_equity < 0.5:
            score += 2
            reasons.append("低负债率")
        elif debt_equity < 1.0:
            score += 1
            reasons.append("可控负债")

        if op_margin > 0.15:
            score += 2
            reasons.append(f"强利润率: {op_margin:.1%}")
        elif op_margin > 0.05:
            score += 1

        if current_ratio > 1.5:
            score += 1
            reasons.append("流动性良好")

        return {"score": score, "max_score": 8, "details": "; ".join(reasons)}

    def _buffett_consistency(self, historical: list[dict]) -> dict:
        """盈利一致性分析"""
        earnings = [
            h.get("net_income", h.get("eps", 0))
            for h in historical
            if h.get("net_income") or h.get("eps")
        ]
        if len(earnings) < 3:
            return {"score": 0, "max_score": 3, "details": "历史数据不足"}

        growing = all(earnings[i] >= earnings[i + 1] for i in range(len(earnings) - 1))
        if growing:
            growth_rate = earnings[0] / max(abs(earnings[-1]), 0.01) - 1
            return {
                "score": 3,
                "max_score": 3,
                "details": f"盈利持续增长({len(earnings)}期), 累计增长{growth_rate:.1%}",
            }
        return {"score": 1, "max_score": 3, "details": "盈利增长不一致"}

    def _buffett_moat(self, historical: list[dict]) -> dict:
        """护城河分析(5维度)"""
        if len(historical) < 3:
            return {"score": 0, "max_score": 5, "details": "数据不足"}

        roes = [h.get("roe", 0) for h in historical if h.get("roe")]
        margins = [h.get("gross_margin", h.get("operating_margin", 0)) for h in historical]

        score = 0
        reasons = []

        # 1. ROE一致性
        if roes:
            high_roe_pct = sum(1 for r in roes if r > 0.15) / len(roes)
            if high_roe_pct >= 0.8:
                score += 2
                reasons.append(f"ROE一致性好({high_roe_pct:.0%}期>15%)")
            elif high_roe_pct >= 0.5:
                score += 1

        # 2. 利润率稳定性
        if len(margins) >= 3:
            avg = sum(margins) / len(margins)
            recent = sum(margins[:2]) / 2
            older = sum(margins[-2:]) / 2
            if avg > 0.2 and recent >= older:
                score += 1
                reasons.append("利润率稳定/提升")
            if avg > 0.3:
                score += 1
                reasons.append(f"高利润率({avg:.1%})")

        # 3. 资产效率
        asset_turnover = historical[0].get("asset_turnover", 0) if historical else 0
        if asset_turnover > 1.0:
            score += 1
            reasons.append("资产效率高")

        return {"score": min(score, 5), "max_score": 5, "details": "; ".join(reasons)}

    def _buffett_pricing_power(self, historical: list[dict]) -> dict:
        """定价权分析"""
        margins = [h.get("gross_margin", 0) for h in historical if h.get("gross_margin")]
        if len(margins) < 3:
            return {"score": 0, "max_score": 5, "details": "数据不足"}

        recent = sum(margins[:2]) / 2
        older = sum(margins[-2:]) / 2
        avg = sum(margins) / len(margins)

        score = 0
        reasons = []
        if recent > older + 0.02:
            score += 3
            reasons.append("毛利率扩张(强定价权)")
        elif recent >= older - 0.01:
            score += 2
            reasons.append("毛利率稳定")

        if avg > 0.50:
            score += 2
            reasons.append(f"高毛利{avg:.0%}(品牌溢价)")
        elif avg > 0.30:
            score += 1

        return {"score": min(score, 5), "max_score": 5, "details": "; ".join(reasons)}

    def _buffett_book_value_growth(self, historical: list[dict]) -> dict:
        """每股净资产增长分析"""
        bvs = [
            h.get("bvps", h.get("book_value_per_share", 0))
            for h in historical
            if h.get("bvps") or h.get("book_value_per_share")
        ]
        if len(bvs) < 3:
            return {"score": 0, "max_score": 5, "details": "数据不足"}

        growing = sum(1 for i in range(len(bvs) - 1) if bvs[i] > bvs[i + 1])
        growth_rate = growing / (len(bvs) - 1)

        score = 0
        if growth_rate >= 0.8:
            score += 3
        elif growth_rate >= 0.5:
            score += 1

        if bvs[-1] > 0 and bvs[0] > bvs[-1]:
            cagr = (bvs[0] / bvs[-1]) ** (1 / (len(bvs) - 1)) - 1
            if cagr > 0.15:
                score += 2
            elif cagr > 0.10:
                score += 1

        return {
            "score": min(score, 5),
            "max_score": 5,
            "details": f"BVPS增长率一致性: {growth_rate:.0%}",
        }

    def _buffett_management(self, f: dict) -> dict:
        """管理层质量评估"""
        score = 0.0
        reasons = []

        buyback = f.get("share_buyback", 0)
        dividends = f.get("dividends_paid", 0)
        insider = f.get("insider_holding_pct", 0)

        if buyback < 0:
            # 回购
            score += 1
            reasons.append("公司回购股份")
        if dividends and dividends > 0:
            score += 1
            reasons.append("持续分红")
        if insider > 5:
            score += 1
            reasons.append("管理层高持股")
        elif insider > 1:
            score += 0.5

        return {
            "score": min(score, 3),
            "max_score": 3,
            "details": "; ".join(reasons) or "无负面信号",
        }

    def _buffett_owner_earnings(self, f: dict, historical: list[dict] | None = None) -> dict:
        """计算所有者收益(巴菲特偏好的真实盈利能力指标)"""
        net_income = f.get("net_income", 0)
        depreciation = f.get("depreciation", 0)
        capex = abs(f.get("capex", f.get("capital_expenditure", 0)))

        maintenance_capex = capex * 0.85  # 假设15%为增长性支出
        if depreciation > 0:
            maintenance_capex = max(maintenance_capex, depreciation)  # 不低于折旧

        # 运营资本变动
        wc_change = f.get("working_capital_change", 0)

        owner_earnings = net_income + depreciation - maintenance_capex - wc_change

        return {
            "owner_earnings": round(owner_earnings, 0),
            "components": {
                "net_income": net_income,
                "depreciation": depreciation,
                "maintenance_capex": round(maintenance_capex, 0),
                "working_capital_change": wc_change,
            },
            "details": f"净利润{net_income:+.0f}+折旧{depreciation:.0f}-维护性支出{maintenance_capex:.0f}",
        }

    def _buffett_intrinsic_value(self, f: dict, historical: list[dict] | None = None) -> dict:
        """三阶段DCF估值(保守参数)"""
        oe_result = self._buffett_owner_earnings(f, historical)
        owner_earnings = oe_result.get("owner_earnings", 0)
        shares = f.get("shares_outstanding", 1)

        if owner_earnings <= 0 or shares <= 0:
            return {"intrinsic_value": None, "details": "数据不足以估值"}

        stage1_growth = min(0.08, max(0.02, f.get("earnings_growth_3y", 5) / 100 * 0.7))
        stage2_growth = stage1_growth * 0.5
        terminal_growth = 0.025
        discount_rate = 0.10
        stage1_years = 5

        # Stage 1
        stage1_pv = sum(
            owner_earnings * (1 + stage1_growth) ** y / (1 + discount_rate) ** y
            for y in range(1, stage1_years + 1)
        )
        # Terminal
        final_oe = owner_earnings * (1 + stage1_growth) ** stage1_years
        terminal_value = final_oe * (1 + terminal_growth) / (discount_rate - terminal_growth)
        terminal_pv = terminal_value / (1 + discount_rate) ** stage1_years

        total_iv = (stage1_pv + terminal_pv) * 0.85  # 15%安全边际折价
        iv_per_share = total_iv / shares

        return {
            "intrinsic_value": round(iv_per_share, 2),
            "raw_iv": round(total_iv / shares, 2),
            "assumptions": {
                "stage1_growth": round(stage1_growth, 3),
                "discount_rate": discount_rate,
                "terminal_growth": terminal_growth,
            },
            "details": f"三阶段DCF: 增长{stage1_growth:.1%}→{stage2_growth:.1%}→{terminal_growth:.1%}, 折现率{discount_rate:.0%}",
        }

    # ════════════════════════════════════════════
    #  4方法综合估值引擎(来源: ai-hedge-fund/valuation.py)
    # ════════════════════════════════════════════

    @staticmethod
    def calculate_intrinsic_value(
        free_cash_flow: float,
        growth_rate: float = 0.05,
        discount_rate: float = 0.10,
        terminal_growth_rate: float = 0.02,
        num_years: int = 5,
    ) -> float:
        """经典DCF估值"""
        if free_cash_flow is None or free_cash_flow <= 0:
            return 0
        pv = sum(
            free_cash_flow * (1 + growth_rate) ** yr / (1 + discount_rate) ** yr
            for yr in range(1, num_years + 1)
        )
        term_val = (
            free_cash_flow * (1 + growth_rate) ** num_years * (1 + terminal_growth_rate)
        ) / (discount_rate - terminal_growth_rate)
        pv_term = term_val / (1 + discount_rate) ** num_years
        return pv + pv_term

    @staticmethod
    def calculate_owner_earnings_value(
        net_income: float,
        depreciation: float,
        capex: float,
        working_capital_change: float = 0,
        growth_rate: float = 0.05,
        required_return: float = 0.15,
        margin_of_safety: float = 0.25,
        num_years: int = 5,
    ) -> float:
        """巴菲特所有者收益估值 + 安全边际"""
        if not all(isinstance(x, (int, float)) for x in [net_income, depreciation, capex]):
            return 0
        owner_earnings = net_income + depreciation - abs(capex) - working_capital_change
        if owner_earnings <= 0:
            return 0
        pv = sum(
            owner_earnings * (1 + growth_rate) ** yr / (1 + required_return) ** yr
            for yr in range(1, num_years + 1)
        )
        terminal_growth = min(growth_rate, 0.03)
        term_val = (owner_earnings * (1 + growth_rate) ** num_years * (1 + terminal_growth)) / (
            required_return - terminal_growth
        )
        pv_term = term_val / (1 + required_return) ** num_years
        return (pv + pv_term) * (1 - margin_of_safety)

    @staticmethod
    def calculate_wacc(
        market_cap: float,
        total_debt: float = 0,
        cash: float = 0,
        interest_coverage: float | None = None,
        beta_proxy: float = 1.0,
        risk_free_rate: float = 0.045,
        market_risk_premium: float = 0.06,
    ) -> float:
        """WACC计算(CAPM + 利息覆盖法估算债务成本)"""
        cost_of_equity = risk_free_rate + beta_proxy * market_risk_premium
        if interest_coverage and interest_coverage > 0:
            cost_of_debt = max(risk_free_rate + 0.01, risk_free_rate + (10 / interest_coverage))
        else:
            cost_of_debt = risk_free_rate + 0.05
        net_debt = max((total_debt or 0) - (cash or 0), 0)
        total_value = market_cap + net_debt
        if total_value > 0:
            wacc = (
                market_cap / total_value * cost_of_equity
                + net_debt / total_value * cost_of_debt * 0.75
            )
        else:
            wacc = cost_of_equity
        return min(max(wacc, 0.06), 0.20)

    @staticmethod
    def calculate_ev_ebitda_value(financials: list[dict]) -> float:
        """EV/EBITDA中位数估值"""
        if not financials:
            return 0
        m0 = financials[0]
        ev = float(m0.get("enterprise_value", 0) or 0)
        ev_ebitda = float(m0.get("ev_to_ebitda", 0) or 0)
        market_cap = float(m0.get("market_cap", 0) or 0)
        if not ev or not ev_ebitda:
            return 0.0
        ebitda_now = ev / ev_ebitda
        multiples = [
            float(m.get("ev_to_ebitda", 0)) for m in financials if m.get("ev_to_ebitda")
        ]
        if not multiples:
            return 0.0
        med_mult = sorted(multiples)[len(multiples) // 2]
        ev_implied = med_mult * ebitda_now
        net_debt = ev - market_cap
        return max(ev_implied - net_debt, 0.0)

    @staticmethod
    def calculate_residual_income_value(
        market_cap: float,
        net_income: float,
        price_to_book: float,
        book_value_growth: float = 0.03,
        cost_of_equity: float = 0.10,
        terminal_growth: float = 0.03,
        num_years: int = 5,
    ) -> float:
        """剩余收益模型(Edwards-Bell-Ohlson)"""
        if not (market_cap and net_income and price_to_book and price_to_book > 0):
            return 0
        book_val = market_cap / price_to_book
        ri0 = net_income - cost_of_equity * book_val
        if ri0 <= 0:
            return 0
        pv_ri = sum(
            ri0 * (1 + book_value_growth) ** yr / (1 + cost_of_equity) ** yr
            for yr in range(1, num_years + 1)
        )
        term_ri = (
            ri0 * (1 + book_value_growth) ** (num_years + 1) / (cost_of_equity - terminal_growth)
        )
        pv_term = term_ri / (1 + cost_of_equity) ** num_years
        return (book_val + pv_ri + pv_term) * 0.8

    def valuation_composite(self, f: dict, historical: list[dict] | None = None) -> dict:
        """综合估值:4方法 + WACC + 情景分析"""
        net_income = f.get("net_income", 0)
        depreciation = f.get("depreciation", 0)
        capex = f.get("capex", f.get("capital_expenditure", 0))
        market_cap = f.get("market_cap", f.get("total_market_cap", 1))
        price = f.get("price", 1)
        shares = f.get("shares_outstanding", 1)
        fcf = f.get("free_cash_flow", net_income * 0.8)
        revenue_growth = f.get("revenue_growth", f.get("earnings_growth_3y", 5) / 100)

        # 1. 所有者收益估值
        oe_val = self.calculate_owner_earnings_value(
            net_income, depreciation, capex, growth_rate=max(0.02, revenue_growth)
        )
        oe_per_share = oe_val / shares if shares > 0 else 0

        # 2. WACC + 增强DCF
        wacc = self.calculate_wacc(
            market_cap,
            f.get("total_debt", 0),
            f.get("cash", 0),
            f.get("interest_coverage"),
            beta_proxy=f.get("beta", 1.0),
        )
        dcf_val = self.calculate_intrinsic_value(fcf, revenue_growth, wacc)
        dcf_per_share = dcf_val / shares if shares > 0 else 0

        # 3. EV/EBITDA
        ev_ebitda_val = self.calculate_ev_ebitda_value(historical or [f])
        ev_per_share = ev_ebitda_val / shares if shares > 0 else 0

        # 4. 剩余收益
        ri_val = self.calculate_residual_income_value(
            market_cap, net_income, f.get("pb_ratio", f.get("price_to_book", 1))
        )
        ri_per_share = ri_val / shares if shares > 0 else 0

        # 综合加权
        methods = []
        if oe_per_share > 0:
            methods.append(("owner_earnings", oe_per_share, 0.35))
        if dcf_per_share > 0:
            methods.append(("enhanced_dcf", dcf_per_share, 0.35))
        if ev_per_share > 0:
            methods.append(("ev_ebitda", ev_per_share, 0.20))
        if ri_per_share > 0:
            methods.append(("residual_income", ri_per_share, 0.10))

        if not methods:
            return {
                "analyst": "valuation",
                "signal": "neutral",
                "composite_value": None,
                "details": "无有效估值方法",
            }

        total_weight = sum(w for _, _, w in methods)
        composite = sum(v * w / total_weight for _, v, w in methods)

        # 安全边际判断
        margin = (composite - price) / price if price > 0 else 0
        signal = "bullish" if margin > 0.25 else ("bearish" if margin < -0.15 else "neutral")

        return {
            "analyst": "valuation_composite",
            "composite_value": round(composite, 2),
            "market_price": price,
            "margin_of_safety_pct": round(margin * 100, 1),
            "signal": signal,
            "wacc": round(wacc, 4),
            "methods": {name: round(val, 2) for name, val, _ in methods},
            "details": f"综合估值{composite:.0f} vs 市价{price:.0f}, 安全边际{margin:.1%}",
        }
