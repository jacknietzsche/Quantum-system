"""
大师Agent适配器 - 将 ai-hedge-fund 的17位投资大师扩展到A股系统
纯Python量化分析,无需LLM调用
与 QuantAnalyzers 互补:本模块提供 Cathie Wood / Ackman / Burry / Druckenmiller 等额外视角
"""

import math

from shared.logging import log_exception


class MasterAgentRegistry:
    """大师Agent注册表 - 管理所有投资大师分析函数"""

    def __init__(self):
        self._agents = {}
        self._register_all()

    def _register_all(self):
        """注册所有大师Agent"""
        agents_map = {
            "cathie_wood": CathieWoodAnalyzer(),
            "bill_ackman": BillAckmanAnalyzer(),
            "michael_burry": MichaelBurryAnalyzer(),
            "stanley_druckenmiller": DruckenmillerAnalyzer(),
            "aswath_damodaran": DamodaranAnalyzer(),
            "phil_fisher": PhilFisherAnalyzer(),
            "rakesh_jhunjhunwala": JhunjhunwalaAnalyzer(),
            "howard_marks": HowardMarksAnalyzer(),
            "joel_greenblatt": GreenblattAnalyzer(),
            "peter_lynch_growth": LynchGrowthAnalyzer(),
            "risk_sentinel": RiskSentinelAnalyzer(),
            "limit_up_master": LimitUpMaster(),
            "momentum_master": MomentumMaster(),
        }
        self._agents = agents_map

    def get_agent(self, name: str):
        return self._agents.get(name)

    def get_all_names(self) -> list[str]:
        return list(self._agents.keys())

    def analyze_all(
        self, stock_code: str, financials: dict, prices: list[float] | None = None
    ) -> list[dict]:
        """运行所有大师Agent分析"""
        results = []
        for _name, agent in self._agents.items():
            try:
                result = agent.analyze(stock_code, financials, prices)
                if not result:
                    continue
                result.setdefault("name", agent.name)
                result.setdefault("display_name", agent.display_name or agent.name)
                result.setdefault("style", agent.style)
                results.append(result)
            except Exception as e:
                log_exception("master_agents", e)
        return results

    def analyze_selected(
        self,
        stock_code: str,
        financials: dict,
        agent_names: list[str],
        prices: list[float] | None = None,
    ) -> list[dict]:
        """运行指定的大师Agent"""
        results = []
        for name in agent_names:
            agent = self._agents.get(name)
            if agent:
                try:
                    result = agent.analyze(stock_code, financials, prices)
                    if result:
                        results.append(result)
                except Exception as e:
                    log_exception("master_agents", e)
        return results


class BaseMasterAnalyzer:
    """大师分析基类"""

    name: str = ""
    display_name: str = ""
    style: str = ""  # value/growth/contrarian/macro/quant/risk

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        raise NotImplementedError


class CathieWoodAnalyzer(BaseMasterAnalyzer):
    """Cathie Wood(木头姐)- 颠覆性创新+高增长容忍"""

    name = "cathie_wood"
    display_name = "Cathie Wood"
    style = "growth"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        revenue_growth = f.get("revenue_growth_3y", 0)
        pe = f.get("pe_ratio", 0)
        gross_margin = f.get("gross_margin", 0)
        market_cap = f.get("total_market_cap", 0)
        operating_margin = f.get("operating_margin", 0)

        score = 0
        # 高增长是核心
        if revenue_growth > 30:
            score += 35
        elif revenue_growth > 20:
            score += 25
        elif revenue_growth > 10:
            score += 10

        if gross_margin > 60:
            score += 25
        elif gross_margin > 40:
            score += 15

        # 对高PE更宽容
        if pe > 0 and pe < 100 and revenue_growth > 15:
            score += 20
        elif pe > 0 and pe < 50:
            score += 10

        # 中小盘更有爆发力
        if 0 < market_cap < 500e8:
            score += 15
        elif 0 < market_cap < 2000e8:
            score += 8

        # 经营利润率改善
        if operating_margin > 10:
            score += 10

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "revenue_growth_3y": revenue_growth,
                "gross_margin": gross_margin,
                "pe": pe,
                "market_cap_yi": round(market_cap, 1),
                "innovation_score": score,
            },
        }


class BillAckmanAnalyzer(BaseMasterAnalyzer):
    """Bill Ackman - 维权投资+集中持仓+管理层驱动"""

    name = "bill_ackman"
    display_name = "Bill Ackman"
    style = "activist"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        roe = f.get("roe", 0)
        debt_equity = f.get("debt_to_equity", 100)
        free_cash_flow = f.get("free_cash_flow", 0)
        market_cap = f.get("total_market_cap", 1)
        operating_margin = f.get("operating_margin", 0)
        insider_holding = f.get("insider_holding_pct", 0)

        score = 0
        if roe > 20:
            score += 20
        elif roe > 12:
            score += 10

        # 自由现金流收益率
        fcf_yield = free_cash_flow / max(market_cap, 1) * 100 if market_cap > 0 else 0
        if fcf_yield > 8:
            score += 30
        elif fcf_yield > 5:
            score += 20
        elif fcf_yield > 2:
            score += 10

        if debt_equity < 40:
            score += 15
        elif debt_equity < 80:
            score += 8

        # 经营利润率
        if operating_margin > 15:
            score += 15
        elif operating_margin > 8:
            score += 8

        if insider_holding > 10:
            score += 15
        elif insider_holding > 3:
            score += 8

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "fcf_yield_pct": round(fcf_yield, 2),
                "roe": roe,
                "debt_equity": debt_equity,
                "operating_margin": operating_margin,
                "activist_score": score,
            },
        }


class MichaelBurryAnalyzer(BaseMasterAnalyzer):
    """Michael Burry - 逆向价值+做空+尾部风险识别"""

    name = "michael_burry"
    display_name = "Michael Burry"
    style = "contrarian"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        pe = f.get("pe_ratio", 100)
        pb = f.get("pb_ratio", 10)
        debt_equity = f.get("debt_to_equity", 100)
        current_ratio = f.get("current_ratio", 1)
        eps = f.get("eps", 0)
        bvps = f.get("bvps", 0)
        price = f.get("price", 1)

        score = 0
        # 深度价值 - 低PE低PB
        if 0 < pe < 10:
            score += 25
        elif 0 < pe < 15:
            score += 15

        if 0 < pb < 1.0:
            score += 25
        elif 0 < pb < 1.5:
            score += 15

        # Graham Number安全边际
        if eps > 0 and bvps > 0:
            graham_number = math.sqrt(22.5 * eps * bvps)
            if price < graham_number * 0.7:
                score += 25
            elif price < graham_number:
                score += 15

        if debt_equity < 30:
            score += 15
        elif debt_equity < 60:
            score += 8

        # 流动性
        if current_ratio > 2.0:
            score += 15
        elif current_ratio > 1.5:
            score += 8

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "pe": pe,
                "pb": pb,
                "debt_equity": debt_equity,
                "current_ratio": current_ratio,
                "graham_number": round(math.sqrt(22.5 * max(eps, 0.01) * max(bvps, 0.01)), 2)
                if eps > 0 and bvps > 0
                else 0,
                "contrarian_score": score,
            },
        }


class DruckenmillerAnalyzer(BaseMasterAnalyzer):
    """Stanley Druckenmiller - 宏观趋势+集中下注+动量"""

    name = "stanley_druckenmiller"
    display_name = "Stanley Druckenmiller"
    style = "macro"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        score = 0
        change_pct = f.get("change_pct", 0)
        turnover_rate = f.get("turnover_rate", 0)
        f.get("volume", 0)
        trend = f.get("trend", "")

        # 趋势动量
        if trend in ("上升", "bullish"):
            score += 30
        elif trend in ("震荡", "neutral"):
            score += 10

        # 价格动量
        if change_pct > 3:
            score += 20
        elif change_pct > 0:
            score += 10

        if turnover_rate > 3:
            score += 15
        elif turnover_rate > 1:
            score += 8

        # 价格序列分析
        if prices and len(prices) >= 20:
            ma5 = sum(prices[-5:]) / 5
            ma20 = sum(prices[-20:]) / 20
            if ma5 > ma20:
                score += 20
            # 波动率
            returns = [
                (prices[i] - prices[i - 1]) / prices[i - 1]
                for i in range(1, len(prices))
                if prices[i - 1] > 0
            ]
            if returns:
                vol = (sum(r**2 for r in returns[-20:]) / min(20, len(returns))) ** 0.5
                if vol < 0.03:
                    score += 15

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "trend": trend,
                "change_pct": change_pct,
                "turnover_rate": turnover_rate,
                "momentum_score": score,
            },
        }


class DamodaranAnalyzer(BaseMasterAnalyzer):
    """Aswath Damodaran - DCF估值+风险溢价+成长合理定价"""

    name = "aswath_damodaran"
    display_name = "Aswath Damodaran"
    style = "valuation"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        pe = f.get("pe_ratio", 0)
        pb = f.get("pb_ratio", 0)
        roe = f.get("roe", 0)
        earnings_growth = f.get("earnings_growth_3y", 0)
        price = f.get("price", 1)
        eps = f.get("eps", 0)

        score = 0
        # PEG估值
        if pe > 0 and earnings_growth > 0:
            peg = pe / earnings_growth
            if peg < 0.8:
                score += 30
            elif peg < 1.2:
                score += 20
            elif peg < 2.0:
                score += 10

        # PB-ROE合理性
        if pb > 0 and roe > 0:
            implied_roe = pb * 10  # 简化隐含ROE
            if roe > implied_roe * 1.2:
                score += 25
            elif roe > implied_roe:
                score += 15

        # 盈利能力
        if eps > 0 and price > 0:
            earnings_yield = eps / price * 100
            if earnings_yield > 8:
                score += 25
            elif earnings_yield > 5:
                score += 15
            elif earnings_yield > 3:
                score += 8

        # 成长溢价合理性
        if earnings_growth > 10 and pe < 30:
            score += 15
        elif earnings_growth > 5 and pe < 20:
            score += 10

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "pe": pe,
                "pb": pb,
                "roe": roe,
                "earnings_growth_3y": earnings_growth,
                "peg": round(pe / max(earnings_growth, 0.1), 2),
                "valuation_score": score,
            },
        }


class PhilFisherAnalyzer(BaseMasterAnalyzer):
    """Phil Fisher - 成长型投资+Scuttlebutt调研+管理层质量"""

    name = "phil_fisher"
    display_name = "Phil Fisher"
    style = "growth"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        revenue_growth = f.get("revenue_growth_3y", 0)
        gross_margin = f.get("gross_margin", 0)
        rd_intensity = f.get("rd_intensity", 0)
        operating_margin = f.get("operating_margin", 0)
        roe = f.get("roe", 0)

        score = 0
        # 持续高增长
        if revenue_growth > 20:
            score += 30
        elif revenue_growth > 10:
            score += 20
        elif revenue_growth > 5:
            score += 10

        if gross_margin > 50:
            score += 25
        elif gross_margin > 35:
            score += 15

        if rd_intensity > 10:
            score += 15
        elif rd_intensity > 5:
            score += 8

        # 经营效率
        if operating_margin > 20:
            score += 15
        elif operating_margin > 10:
            score += 8

        # ROE
        if roe > 20:
            score += 15
        elif roe > 12:
            score += 8

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "revenue_growth_3y": revenue_growth,
                "gross_margin": gross_margin,
                "operating_margin": operating_margin,
                "roe": roe,
                "growth_quality_score": score,
            },
        }


class JhunjhunwalaAnalyzer(BaseMasterAnalyzer):
    """Rakesh Jhunjhunwala - 印度巴菲特+价值+管理层信任"""

    name = "rakesh_jhunjhunwala"
    display_name = "Rakesh Jhunjhunwala"
    style = "value"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        roe = f.get("roe", 0)
        pe = f.get("pe_ratio", 0)
        debt_equity = f.get("debt_to_equity", 100)
        market_cap = f.get("total_market_cap", 0)
        earnings_growth = f.get("earnings_growth_3y", 0)

        score = 0
        # 高ROE
        if roe > 20:
            score += 30
        elif roe > 15:
            score += 20
        elif roe > 10:
            score += 10

        # 合理PE
        if 0 < pe < 20:
            score += 20
        elif 0 < pe < 35:
            score += 10

        # 低杠杆
        if debt_equity < 30:
            score += 15
        elif debt_equity < 60:
            score += 8

        if 0 < market_cap < 1000e8:
            score += 15
        elif 0 < market_cap < 5000e8:
            score += 8

        # 盈利增长
        if earnings_growth > 15:
            score += 20
        elif earnings_growth > 8:
            score += 10

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "roe": roe,
                "pe": pe,
                "debt_equity": debt_equity,
                "earnings_growth_3y": earnings_growth,
                "value_score": score,
            },
        }


class HowardMarksAnalyzer(BaseMasterAnalyzer):
    """Howard Marks - 市场周期+第二层次思维+风险控制"""

    name = "howard_marks"
    display_name = "Howard Marks"
    style = "cycle"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        pe = f.get("pe_ratio", 0)
        pb = f.get("pb_ratio", 0)
        change_pct = f.get("change_pct", 0)
        volatility = f.get("volatility", 0)
        debt_equity = f.get("debt_to_equity", 100)

        score = 0
        if change_pct < -5 and 0 < pe < 20:
            score += 30  # 恐慌中的价值
        elif change_pct < -2 and 0 < pe < 15:
            score += 20

        if 0 < pb < 1.5:
            score += 20
        elif 0 < pb < 2.5:
            score += 10

        if 0 < volatility < 25:
            score += 15
        elif 0 < volatility < 40:
            score += 8

        # 财务稳健
        if debt_equity < 40:
            score += 15
        elif debt_equity < 70:
            score += 8

        if change_pct < -10 and pe > 0 and pe < 12:
            score += 20

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "pe": pe,
                "pb": pb,
                "change_pct": change_pct,
                "volatility": volatility,
                "debt_equity": debt_equity,
                "cycle_score": score,
            },
        }


class GreenblattAnalyzer(BaseMasterAnalyzer):
    """Joel Greenblatt - 魔法公式(高ROIC+低EV/EBITDA)"""

    name = "joel_greenblatt"
    display_name = "Joel Greenblatt"
    style = "quant"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        roe = f.get("roe", 0)
        pe = f.get("pe_ratio", 0)
        operating_margin = f.get("operating_margin", 0)
        f.get("total_market_cap", 0)
        net_income = f.get("net_income", 0)

        score = 0
        if roe > 25:
            score += 30
        elif roe > 15:
            score += 20
        elif roe > 10:
            score += 10

        if 0 < pe < 10:
            score += 30
        elif 0 < pe < 15:
            score += 20
        elif 0 < pe < 20:
            score += 10

        # 高经营利润率
        if operating_margin > 20:
            score += 20
        elif operating_margin > 10:
            score += 10

        # 盈利为正
        if net_income > 0:
            score += 10

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "roe": roe,
                "pe": pe,
                "operating_margin": operating_margin,
                "magic_formula_score": score,
            },
        }


class LynchGrowthAnalyzer(BaseMasterAnalyzer):
    """Peter Lynch成长版 - 寻找Ten-Bagger+GARP策略"""

    name = "peter_lynch_growth"
    display_name = "Peter Lynch (Growth)"
    style = "growth"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        pe = f.get("pe_ratio", 0)
        earnings_growth = f.get("earnings_growth_3y", 0)
        revenue_growth = f.get("revenue_growth_3y", 0)
        market_cap = f.get("total_market_cap", 0)
        gross_margin = f.get("gross_margin", 0)

        score = 0
        if pe > 0 and earnings_growth > 0:
            peg = pe / earnings_growth
            if peg < 0.5:
                score += 35
            elif peg < 1.0:
                score += 25
            elif peg < 1.5:
                score += 15

        # 高增长
        if revenue_growth > 25:
            score += 25
        elif revenue_growth > 15:
            score += 15
        elif revenue_growth > 8:
            score += 8

        if 0 < market_cap < 300e8:
            score += 20
        elif 0 < market_cap < 1000e8:
            score += 12

        # 毛利率改善
        if gross_margin > 40:
            score += 15
        elif gross_margin > 25:
            score += 8

        signal = "bullish" if score >= 55 else "bearish" if score < 25 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": signal,
            "details": {
                "pe": pe,
                "earnings_growth_3y": earnings_growth,
                "revenue_growth_3y": revenue_growth,
                "peg": round(pe / max(earnings_growth, 0.1), 2),
                "tenbagger_score": score,
            },
        }


class RiskSentinelAnalyzer(BaseMasterAnalyzer):
    """风险哨兵 - 综合风险评估(融合Taleb+Munger风险视角)"""

    name = "risk_sentinel"
    display_name = "Risk Sentinel"
    style = "risk"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        debt_equity = f.get("debt_to_equity", 100)
        current_ratio = f.get("current_ratio", 1)
        cash_ratio = f.get("cash_ratio", 0)
        volatility = f.get("volatility", 0)
        pe = f.get("pe_ratio", 0)
        change_pct = f.get("change_pct", 0)

        risk_score = 0  # 高分 = 高风险

        # 杠杆风险
        if debt_equity > 150:
            risk_score += 30
        elif debt_equity > 80:
            risk_score += 15

        # 流动性风险
        if current_ratio < 1.0:
            risk_score += 25
        elif current_ratio < 1.5:
            risk_score += 12

        # 现金不足
        if cash_ratio < 5:
            risk_score += 15
        elif cash_ratio < 10:
            risk_score += 8

        # 高波动风险
        if volatility > 50:
            risk_score += 20
        elif volatility > 30:
            risk_score += 10

        # 估值泡沫风险
        if pe > 100:
            risk_score += 15
        elif pe > 60:
            risk_score += 8

        # 暴跌风险
        if change_pct < -8:
            risk_score += 15
        elif change_pct < -4:
            risk_score += 8

        # 反转信号:高分 = 高风险 = bearish
        safety_score = max(0, 100 - risk_score)
        signal = "bearish" if risk_score >= 50 else "bullish" if risk_score < 20 else "neutral"
        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "score": safety_score,
            "signal": signal,
            "details": {
                "debt_equity": debt_equity,
                "current_ratio": current_ratio,
                "cash_ratio": cash_ratio,
                "volatility": volatility,
                "pe": pe,
                "risk_score": risk_score,
            },
        }


class LimitUpMaster(BaseMasterAnalyzer):
    """涨停大师 - 短线博弈专家"""

    name = "limit_up_master"
    display_name = "涨停大师"
    style = "limit_up"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        turnover = f.get("turnover_rate", 0)
        volume_ratio = f.get("daily_volume_ratio", 0)
        change_pct = f.get("change_pct", 0)
        pe = f.get("pe_ratio", 0)

        score = 0
        if turnover >= 15:
            score += 35
        elif turnover >= 10:
            score += 25
        elif turnover >= 5:
            score += 15
        if volume_ratio >= 2.0:
            score += 25
        elif volume_ratio >= 1.5:
            score += 20
        elif volume_ratio >= 1.2:
            score += 10
        if 5 <= change_pct <= 9:
            score += 25
        elif change_pct >= 9:
            score += 20
        elif 2 <= change_pct < 5:
            score += 15
        if 0 < pe <= 30:
            score += 15
        elif pe <= 0 or pe > 60:
            score -= 10

        score = max(0, min(100, score))
        signal = "买入" if score >= 70 else ("持有" if score >= 50 else "观望")
        reasoning = f"换手{turnover:.1f}%/量比{volume_ratio:.1f}/涨幅{change_pct:.1f}%"

        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "name": self.name,
            "display_name": self.display_name,
            "style": self.style,
            "score": score,
            "signal": signal,
            "reasoning": reasoning,
            "metrics": {
                "turnover": turnover,
                "volume_ratio": volume_ratio,
                "change_pct": change_pct,
            },
        }


class MomentumMaster(BaseMasterAnalyzer):
    """动量大师 - 中期趋势专家"""

    name = "momentum_master"
    display_name = "动量大师"
    style = "momentum"

    def analyze(self, stock_code: str, f: dict, prices: list[float] | None = None) -> dict:
        roe = f.get("roe", 0)
        revenue_growth = f.get("revenue_growth_3y", 0)
        pe = f.get("pe_ratio", 0)

        trend_s = 0
        rsi_v = 50
        if prices and len(prices) >= 20:
            try:
                from services.trend_analyzer import rsi, trend_strength

                trend_s = trend_strength(prices)
                rsi_result = rsi(prices)
                rsi_v = rsi_result[-1] if isinstance(rsi_result, list) else rsi_result
            except Exception as e:
                log_exception("master_agents", e)

        score = 0
        if trend_s >= 70:
            score += 35
        elif trend_s >= 50:
            score += 25
        elif trend_s >= 30:
            score += 15
        if 40 <= rsi_v <= 70:
            score += 20
        elif rsi_v >= 70:
            score += 10
        elif rsi_v <= 30:
            score += 5
        if revenue_growth >= 30:
            score += 25
        elif revenue_growth >= 15:
            score += 20
        elif revenue_growth >= 5:
            score += 10
        if roe >= 20:
            score += 15
        elif roe >= 10:
            score += 10
        if 0 < pe <= 40:
            score += 5

        score = max(0, min(100, score))
        signal = "买入" if score >= 65 else ("持有" if score >= 45 else "观望")
        reasoning = f"趋势{trend_s:.0f}/RSI{rsi_v:.0f}/成长{revenue_growth:.0f}%"

        return {
            "analyst": self.name,
            "stock_code": stock_code,
            "name": self.name,
            "display_name": self.display_name,
            "style": self.style,
            "score": score,
            "signal": signal,
            "reasoning": reasoning,
            "metrics": {
                "trend_strength": trend_s,
                "rsi": rsi_v,
                "revenue_growth": revenue_growth,
            },
        }


# 全局单例
_global_registry: MasterAgentRegistry | None = None


def get_master_agents() -> MasterAgentRegistry:
    global _global_registry  # noqa: PLW0603
    if _global_registry is None:
        _global_registry = MasterAgentRegistry()
    return _global_registry


# ── AI 增强接口 (Phase 2, 不修改已有类) ──


def create_ai_agent(
    name: str,
    llm_client=None,
    tools=None,
) -> object | None:
    """创建 AI 增强的大师 Agent

    将已有的规则型大师 Agent 包装为 AI Agent:
    - 有 LLM 时调用工具 + LLM 推理
    - 无 LLM 时回退到原有规则评分

    Args:
        name: 大师名称 (如 "cathie_wood")
        llm_client: LLM 客户端实例 (可选)
        tools: AgentTools 实例 (可选)

    Returns:
        AIAgent 实例, 或 None (名称不存在时)
    """
    agent = get_master_agents().get_agent(name)
    if agent is None:
        return None

    from services.screening.ai_agents import AIAgent

    return AIAgent(
        name=getattr(agent, "name", name),
        display_name=getattr(agent, "display_name", name),
        style=getattr(agent, "style", ""),
        llm_client=llm_client,
        rule_agent=agent,
        tools=tools,
    )


def get_ai_master_agents(llm_client=None, tools=None) -> dict[str, object]:
    """获取所有 AI 增强的大师 Agent

    Returns:
        {name: AIAgent} 字典
    """
    agents = {}
    for name in get_master_agents().get_all_names():
        ai_agent = create_ai_agent(name, llm_client=llm_client, tools=tools)
        if ai_agent:
            agents[name] = ai_agent
    return agents


def analyze_with_ai(
    name: str,
    stock_code: str,
    financials: dict,
    prices: list[float] | None = None,
    llm_client=None,
) -> dict:
    """使用 AI 增强的大师 Agent 分析股票

    便捷函数: 创建 AI Agent -> 分析 -> 返回结果。
    无 LLM 时自动回退到规则评分。

    Args:
        name: 大师名称
        stock_code: 股票代码
        financials: 财务数据字典
        prices: 历史价格列表 (可选)
        llm_client: LLM 客户端 (可选)

    Returns:
        标准格式的分析结果
    """
    ai_agent = create_ai_agent(name, llm_client=llm_client)
    if ai_agent is None:
        return {
            "name": name,
            "stock_code": stock_code,
            "score": 50,
            "signal": "neutral",
            "reasoning": f"Unknown agent: {name}",
        }
    return ai_agent.analyze(stock_code, financials, prices)
