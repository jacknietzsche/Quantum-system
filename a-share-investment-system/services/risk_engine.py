"""风控引擎 - 波动率调整+相关性矩阵+集中度检查+压力测试 - 来源: ai-hedge-fund + Taleb-skill"""

import math
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


class RiskEngine(BaseService):
    """三层风控引擎 - 纯Python计算,无需LLM"""

    # 波动率→仓位限额映射
    VOL_LIMITS: ClassVar[list[tuple[float, float]]] = [
        (0.15, 0.25),  # vol < 15% in stock cap 25%
        (0.30, 0.15),  # vol < 30% in stock cap 15%
        (0.50, 0.10),  # vol < 50% in stock cap 10%
        (float("inf"), 0.05),  # vol >= 50% in stock cap 5%
    ]

    # 相关性→乘数映射
    CORR_MULTIPLIERS: ClassVar[list[tuple[float, float]]] = [
        (0.80, 0.70),  # avg_corr >= 0.8 → x0.70
        (0.60, 0.85),  # avg_corr >= 0.6 → x0.85
        (0.40, 1.00),  # avg_corr >= 0.4 → x1.00
        (0.20, 1.05),  # avg_corr >= 0.2 → x1.05
        (0.00, 1.10),  # avg_corr < 0.2  → x1.10
    ]

    def full_audit(
        self,
        portfolio: list[dict],
        market_regime: dict | None = None,
        candidate_orders: list[dict] | None = None,
        price_history: pd.DataFrame = None,
    ) -> ServiceResult:
        """执行完整三层风控审计"""
        try:
            regime = market_regime or {}
            audit: dict[str, Any] = {
                "pass": True,
                "market_risk": self._audit_market(regime),
                "stock_risks": self._audit_stocks(portfolio),
                "portfolio_risk": self._audit_portfolio(portfolio, price_history),
                "position_limits": self._calc_position_limits(portfolio, price_history),
            }

            # 综合判定
            reasons = []
            if not audit["market_risk"]["pass"]:
                reasons.append("市场风险未通过")
                audit["pass"] = False
            if not audit["portfolio_risk"]["pass"]:
                reasons.append("组合风险未通过")
                audit["pass"] = False

            audit["reasons"] = reasons
            audit["risk_level"] = self._overall_level(audit)

            return ServiceResult.ok(data=audit)
        except Exception as e:
            return ServiceResult.error(errors=[f"RiskEngine audit failed: {e}"])

    def _audit_market(self, regime: dict) -> dict:
        """第一层:市场风险"""
        reg = regime.get("regime", "NEUTRAL")
        score = regime.get("total_score", 0)

        if reg == "PANIC":
            return {
                "level": "EXTREME",
                "pass": False,
                "score": abs(score) * 50,
                "message": "市场恐慌,建议仓位≤10%",
            }
        if reg == "BEAR":
            return {
                "level": "HIGH",
                "pass": True,
                "score": abs(score) * 40,
                "message": "熊市环境,建议仓位≤30%",
            }
        if reg == "OVERHEAT":
            return {
                "level": "HIGH",
                "pass": True,
                "score": abs(score) * 30,
                "message": "市场过热,注意回撤风险",
            }
        if reg == "BULL":
            return {
                "level": "LOW",
                "pass": True,
                "score": 10,
                "message": "牛市环境,可积极配置",
            }
        return {"level": "MEDIUM", "pass": True, "score": 25, "message": "中性市场"}

    def _audit_stocks(self, portfolio: list[dict]) -> dict[str, dict]:
        """第二层:个股风险"""
        risks: dict[str, dict[str, Any]] = {}
        for h in portfolio:
            code = h.get("stock_code", "")
            risks[code] = {
                "level": "MEDIUM",
                "liquidity_risk": self._check_liquidity(h),
                "concentration_risk": self._check_concentration(h, portfolio),
            }

            # 黑天鹅脆弱性检查
            alerts: list[str] = []
            if h.get("debt_to_equity", 0) > 100:
                alerts.append("高杠杆风险")
            if h.get("pledge_ratio", 0) > 30:
                alerts.append("高质押风险")
            if h.get("cash_to_assets", 20) < 5:
                alerts.append("低现金风险")

            if len(alerts) >= 2:
                risks[code]["level"] = "HIGH"
            risks[code]["alerts"] = alerts

        return risks

    def _audit_portfolio(self, portfolio: list[dict], price_history: pd.DataFrame = None) -> dict:
        """第三层:组合风险"""
        if not portfolio:
            return {"pass": True, "level": "LOW", "message": "空仓"}

        # 波动率调整
        vol_limit = self._volatility_limit(price_history) if price_history is not None else 0.20

        # 相关性分析
        corr_mult = 1.0
        if price_history is not None and len(portfolio) >= 2:
            corr_mult = self._correlation_multiplier(price_history)

        # 集中度检查
        total_value = sum(h.get("current_value", h.get("cost_value", 0)) for h in portfolio)
        max_single_weight = 0.0
        for h in portfolio:
            value = h.get("current_value", h.get("cost_value", 0))
            weight = value / total_value if total_value > 0 else 0
            max_single_weight = max(max_single_weight, weight)

        # 行业集中度
        industries: dict[str, float] = {}
        for h in portfolio:
            ind = h.get("industry", "未知")
            val = h.get("current_value", h.get("cost_value", 0))
            industries[ind] = industries.get(ind, 0) + val
        max_industry_weight = (
            max(industries.values()) / total_value if total_value > 0 and industries else 0
        )

        effective_limit = vol_limit * corr_mult

        issues = []
        if max_single_weight > effective_limit:
            issues.append(f"单股集中度{max_single_weight:.0%} > 限额{effective_limit:.0%}")
        if max_industry_weight > 0.30:
            issues.append(f"行业集中度{max_industry_weight:.0%} > 30%")

        stress_result = self._stress_test(portfolio)

        return {
            "pass": len(issues) == 0,
            "level": "HIGH" if len(issues) >= 2 else ("MEDIUM" if issues else "LOW"),
            "vol_limit": round(vol_limit, 3),
            "corr_mult": round(corr_mult, 3),
            "effective_limit": round(effective_limit, 3),
            "max_single_weight": round(max_single_weight, 3),
            "max_industry_weight": round(max_industry_weight, 3),
            "issues": issues,
            "stress_test": stress_result,
        }

    def _calc_position_limits(
        self, portfolio: list[dict], price_history: pd.DataFrame = None
    ) -> dict:
        """计算仓位限制"""
        vol_limit = self._volatility_limit(price_history) if price_history is not None else 0.20
        corr_mult = (
            self._correlation_multiplier(price_history) if price_history is not None else 1.0
        )
        n_stocks = len(portfolio)

        return {
            "max_single_stock_pct": round(vol_limit * corr_mult * 100, 1),
            "max_total_position_pct": round(
                min(0.95, 1.0 / max(n_stocks, 1) * n_stocks * 0.5) * 100, 1
            ),
            "recommended_stock_count": max(3, min(10, int(1.0 / max(vol_limit, 0.05)))),
            "barbell_advice": (
                "90%低风险(现金+高股息)+10%高成长" if vol_limit < 0.10 else "70%核心+30%卫星"
            ),
        }

    def _volatility_limit(self, price_history: pd.DataFrame) -> float:
        """计算波动率调整后的单股仓位上限"""
        try:
            returns = price_history.pct_change().dropna()
            if len(returns.columns) == 0:
                return 0.20
            vol = float(returns.std().mean() * math.sqrt(252))
            for threshold, limit in self.VOL_LIMITS:
                if vol < threshold:
                    return limit
            return 0.05
        except Exception as e:
            emit_log("ERROR", "risk_engine", f"Operation failed: {str(e)[:100]}")
            return 0.20

    def _correlation_multiplier(self, price_history: pd.DataFrame) -> float:
        """计算相关性矩阵调整乘数"""
        try:
            returns = price_history.pct_change().dropna()
            if returns.shape[1] < 2:
                return 1.0
            corr = returns.corr()
            avg_corr = float(corr.values[np.triu_indices_from(corr.values, k=1)].mean())
            for threshold, multiplier in self.CORR_MULTIPLIERS:
                if avg_corr >= threshold:
                    return multiplier
            return 1.10
        except Exception as e:
            emit_log("ERROR", "risk_engine", f"Operation failed: {str(e)[:100]}")
            return 1.0

    def _check_liquidity(self, holding: dict) -> str:
        """检查个股流动性"""
        turnover = holding.get("turnover_rate", 3)
        market_cap = holding.get("market_cap", 100)
        if turnover < 0.3:
            return "HIGH: 日均换手<0.3%"
        if market_cap < 20:
            return "MEDIUM: 市值<20亿"
        return "LOW"

    def _check_concentration(self, holding: dict, portfolio: list[dict]) -> str:
        """检查个股在组合中的集中度"""
        total_value = sum(h.get("current_value", h.get("cost_value", 0)) for h in portfolio)
        stock_value = holding.get("current_value", holding.get("cost_value", 0))
        weight = stock_value / total_value if total_value > 0 else 0
        if weight > 0.25:
            return "HIGH: 单股权重>25%"
        if weight > 0.15:
            return "MEDIUM: 单股权重>15%"
        return "LOW"

    def _stress_test(self, portfolio: list[dict]) -> dict:
        """压力测试:模拟极端回撤场景"""
        if not portfolio:
            return {"scenario": "N/A", "estimated_loss_pct": 0}

        total_value = sum(h.get("current_value", h.get("cost_value", 0)) for h in portfolio)
        stressed_value = total_value * 0.80  # -20% shock

        crash_value = total_value * 0.60

        return {
            "scenario": "20% market decline",
            "estimated_loss_pct": -20.0,
            "stressed_portfolio_value": round(stressed_value, 0),
            "crash_scenario_loss_pct": -40.0,
            "crash_portfolio_value": round(crash_value, 0),
            "recovery_needed_pct": round((total_value / max(crash_value, 1) - 1) * 100, 1),
        }

    def _overall_level(self, audit: dict) -> str:
        """综合风险等级"""
        market = audit.get("market_risk", {}).get("level", "MEDIUM")
        portfolio = audit.get("portfolio_risk", {}).get("level", "MEDIUM")
        levels = {"EXTREME": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        max_level = max(levels.get(market, 2), levels.get(portfolio, 2))
        return ["LOW", "MEDIUM", "HIGH", "EXTREME"][max_level - 1]

    def assess_stock_risk(self, stock_code: str, stock_data: dict) -> ServiceResult:
        """个股风险评估 - 综合波动率/估值/流动性/财务"""
        try:
            risk_score = 0
            risk_factors = []

            # 1. 波动率风险
            volatility = stock_data.get("volatility_20d", 0)
            if volatility > 0.5:
                risk_score += 30
                risk_factors.append(f"极高波动率(年化>{volatility:.0%})")
            elif volatility > 0.3:
                risk_score += 20
                risk_factors.append(f"高波动率(年化>{volatility:.0%})")
            elif volatility > 0.15:
                risk_score += 10

            # 2. 估值风险
            pe = stock_data.get("pe", 0)
            if pe and pe > 200:
                risk_score += 25
                risk_factors.append(f"估值泡沫(PE={pe:.0f})")
            elif pe and pe > 100:
                risk_score += 15
                risk_factors.append(f"高估值(PE={pe:.0f})")
            elif pe and pe < 0:
                risk_score += 20
                risk_factors.append("亏损状态(PE<0)")

            # 3. 流动性风险
            turnover = stock_data.get("turnover_rate", 3)
            market_cap = stock_data.get("market_cap", 100)
            if turnover < 0.3:
                risk_score += 20
                risk_factors.append("低流动性(换手率<0.3%)")
            if market_cap and market_cap < 20:
                risk_score += 15
                risk_factors.append(f"小市值({market_cap:.0f}亿)")

            # 4. 财务风险
            debt_ratio = stock_data.get("debt_to_equity", 0)
            if debt_ratio and debt_ratio > 200:
                risk_score += 20
                risk_factors.append(f"高杠杆(资产负债率>{debt_ratio / 100:.0%})")
            roe = stock_data.get("roe", 10)
            if roe and roe < 0:
                risk_score += 15
                risk_factors.append("ROE为负")

            # 5. 技术面风险
            rsi = stock_data.get("rsi_14", 50)
            if rsi and rsi > 80:
                risk_score += 10
                risk_factors.append(f"RSI超买({rsi:.0f})")
            elif rsi and rsi < 20:
                risk_score += 5
                risk_factors.append(f"RSI超卖({rsi:.0f})")

            # 风险等级
            if risk_score >= 60:
                level = "HIGH"
            elif risk_score >= 30:
                level = "MEDIUM"
            else:
                level = "LOW"

            return ServiceResult.ok(
                data={
                    "stock_code": stock_code,
                    "risk_score": risk_score,
                    "risk_level": level,
                    "risk_factors": risk_factors,
                    "factor_count": len(risk_factors),
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"assess_stock_risk failed: {e}"])

    def calculate_var(
        self, returns: pd.Series, confidence: float = 0.95, holding_period: int = 1
    ) -> ServiceResult:
        """计算VaR (Value at Risk) - 历史模拟法 + 参数法"""
        try:
            if returns is None or len(returns) < 10:
                return ServiceResult.error(errors=["insufficient data for VaR calculation"])

            clean_returns = returns.dropna()
            if len(clean_returns) < 10:
                return ServiceResult.error(errors=["insufficient clean data for VaR"])

            # 历史模拟法
            sorted_returns = clean_returns.sort_values()
            idx = int((1 - confidence) * len(sorted_returns))
            historical_var = -sorted_returns.iloc[idx]

            # 参数法 (假设正态分布)  # noqa: ERA001
            mu = clean_returns.mean()
            sigma = clean_returns.std()
            from scipy import stats as sp_stats

            z_score = sp_stats.norm.ppf(1 - confidence)
            parametric_var = -(mu + z_score * sigma)

            # 调整持有期
            historical_var_adj = historical_var * math.sqrt(holding_period)
            parametric_var_adj = parametric_var * math.sqrt(holding_period)

            # CVaR (条件VaR / Expected Shortfall)
            tail = sorted_returns.iloc[: idx + 1]
            cvar = -tail.mean() if len(tail) > 0 else historical_var

            return ServiceResult.ok(
                data={
                    "confidence": confidence,
                    "holding_period_days": holding_period,
                    "historical_var": round(float(historical_var_adj) * 100, 2),
                    "parametric_var": round(float(parametric_var_adj) * 100, 2),
                    "cvar": round(float(cvar * math.sqrt(holding_period)) * 100, 2),
                    "daily_vol": round(float(sigma) * 100, 2),
                    "annual_vol": round(float(sigma * math.sqrt(252)) * 100, 2),
                    "observations": len(clean_returns),
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"calculate_var failed: {e}"])

    def risk_alerts(
        self, portfolio: list[dict], market_regime: dict | None = None
    ) -> ServiceResult:
        """生成风险预警列表"""
        try:
            alerts = []
            regime = market_regime or {}

            # 1. 市场级预警
            reg = regime.get("regime", "NEUTRAL")
            if reg in ("PANIC", "BEAR"):
                alerts.append(
                    {
                        "type": "MARKET",
                        "level": "HIGH" if reg == "PANIC" else "MEDIUM",
                        "message": f"市场环境: {reg}，建议降低仓位",
                        "action": "减仓至50%以下" if reg == "PANIC" else "控制仓位在70%以下",
                    }
                )

            # 2. 组合级预警
            total_value = sum(h.get("current_value", h.get("cost_value", 0)) for h in portfolio)

            for h in portfolio:
                code = h.get("stock_code", "")
                name = h.get("stock_name", code)
                value = h.get("current_value", h.get("cost_value", 0))
                weight = value / total_value if total_value > 0 else 0
                pnl_pct = h.get("profit_loss_pct", 0)

                # 单股集中度预警
                if weight > 0.25:
                    alerts.append(
                        {
                            "type": "CONCENTRATION",
                            "level": "HIGH",
                            "message": f"{name}({code}) 仓位{weight:.1%}超过25%",
                            "action": "建议减仓至20%以下",
                        }
                    )
                elif weight > 0.15:
                    alerts.append(
                        {
                            "type": "CONCENTRATION",
                            "level": "MEDIUM",
                            "message": f"{name}({code}) 仓位{weight:.1%}偏高",
                            "action": "关注仓位控制",
                        }
                    )

                # 止损预警
                if pnl_pct < -15:
                    alerts.append(
                        {
                            "type": "STOP_LOSS",
                            "level": "HIGH",
                            "message": f"{name}({code}) 浮亏{pnl_pct:.1f}%触发止损线",
                            "action": "建议止损卖出",
                        }
                    )
                elif pnl_pct < -8:
                    alerts.append(
                        {
                            "type": "STOP_LOSS",
                            "level": "MEDIUM",
                            "message": f"{name}({code}) 浮亏{pnl_pct:.1f}%接近止损线",
                            "action": "密切关注，准备止损",
                        }
                    )

                # 止盈预警
                if pnl_pct > 30:
                    alerts.append(
                        {
                            "type": "TAKE_PROFIT",
                            "level": "MEDIUM",
                            "message": f"{name}({code}) 浮盈{pnl_pct:.1f}%可考虑止盈",
                            "action": "考虑分批止盈锁定利润",
                        }
                    )

            # 3. 行业集中度
            industry_weights: dict[str, float] = {}
            for h in portfolio:
                ind = h.get("industry", "未知")
                value = h.get("current_value", h.get("cost_value", 0))
                industry_weights[ind] = industry_weights.get(ind, 0) + value
            for ind, val in industry_weights.items():
                ind_weight = val / total_value if total_value > 0 else 0
                if ind_weight > 0.4:
                    alerts.append(
                        {
                            "type": "INDUSTRY",
                            "level": "HIGH",
                            "message": f"行业{ind}集中度{ind_weight:.1%}过高",
                            "action": "建议分散行业配置",
                        }
                    )

            # 按严重程度排序
            level_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
            alerts.sort(key=lambda a: level_order.get(a["level"], 1))

            return ServiceResult.ok(
                data={
                    "total_alerts": len(alerts),
                    "high_alerts": sum(1 for a in alerts if a["level"] == "HIGH"),
                    "medium_alerts": sum(1 for a in alerts if a["level"] == "MEDIUM"),
                    "alerts": alerts,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"risk_alerts failed: {e}"])

    def portfolio_var(self, portfolio: list[dict], confidence: float = 0.95) -> ServiceResult:
        """计算组合整体VaR"""
        try:
            total_value = sum(h.get("current_value", h.get("cost_value", 0)) for h in portfolio)
            if total_value <= 0:
                return ServiceResult.ok(data={"portfolio_var": 0, "total_value": 0})

            # 简化: 用个股波动率加权估算  # noqa: ERA001
            weighted_vol = 0
            for h in portfolio:
                value = h.get("current_value", h.get("cost_value", 0))
                weight = value / total_value
                vol = h.get("volatility", 0.3)  # 默认30%年化波动
                weighted_vol += (weight * vol) ** 2

            portfolio_vol = math.sqrt(weighted_vol)
            from scipy import stats as sp_stats

            z = sp_stats.norm.ppf(confidence)
            var_pct = z * portfolio_vol / math.sqrt(252)  # 日VaR
            var_amount = total_value * var_pct

            return ServiceResult.ok(
                data={
                    "total_value": round(total_value, 0),
                    "portfolio_annual_vol": round(portfolio_vol * 100, 2),
                    "daily_var_pct": round(var_pct * 100, 2),
                    "daily_var_amount": round(var_amount, 0),
                    "confidence": confidence,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"portfolio_var failed: {e}"])
