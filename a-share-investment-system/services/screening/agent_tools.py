"""AI Agent 工具集

每个工具是 AI Agent 可调用的确定性函数，返回结构化 dict。
工具不依赖 LLM，只做数据查询和计算。
"""

from __future__ import annotations

from typing import Any


class AgentTools:
    """Agent 可调用的工具集

    用法:
        tools = AgentTools()
        risk = tools.risk_scan("600519")
        fin = tools.financial_health("600519")
    """

    def __init__(self, db_session: Any | None = None, factor_farm: Any | None = None):
        self._db_session = db_session
        self._factor_farm = factor_farm

    # ── 工具1: 因子计算器 ──

    def calc_factor(self, stock_code: str, factor_name: str) -> dict:
        """计算指定股票的技术/基本面因子值

        Args:
            stock_code: 股票代码 (如 "600519")
            factor_name: 因子名称 (如 "momentum", "volatility", "value")

        Returns:
            {"stock_code": str, "factor_name": str, "value": float, "rank": str}
        """
        try:
            farm = self._factor_farm
            if farm is None:
                from services.factor_farm import FactorFarm

                farm = FactorFarm()
            # 尝试获取因子评估
            result = farm.evaluate_factor(factor_name)
            if result.status == "ok":
                factor_info = result.data.get("factor", {})
                return {
                    "stock_code": stock_code,
                    "factor_name": factor_name,
                    "value": factor_info.get("ic_mean", 0),
                    "rank": "unknown",
                    "category": factor_info.get("category", ""),
                    "description": factor_info.get("description", ""),
                }
            return {
                "stock_code": stock_code,
                "factor_name": factor_name,
                "value": 0,
                "rank": "unavailable",
                "note": f"Factor '{factor_name}' not found in registry",
            }
        except Exception as e:
            return {
                "stock_code": stock_code,
                "factor_name": factor_name,
                "value": 0,
                "rank": "error",
                "error": str(e)[:120],
            }

    # ── 工具2: 财务分析器 ──

    def financial_health(self, stock_code: str) -> dict:
        """从 DB 提取财务指标趋势，评估财务健康度

        Returns:
            {stock_code, ratios, trends, score, signal}
        """
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            try:
                row = session.query(StockInfo).filter(StockInfo.stock_code == stock_code).first()
                if not row:
                    return {"stock_code": stock_code, "error": "not found"}

                ratios = {
                    "pe_ratio": float(row.pe_ratio or 0),
                    "pb_ratio": float(row.pb_ratio or 0),
                    "roe": float(row.roe or 0),
                    "gross_margin": float(row.gross_margin or 0),
                    "operating_margin": float(row.operating_margin or 0),
                    "debt_to_equity": float(row.debt_to_equity or 0),
                    "current_ratio": float(row.current_ratio or 1),
                    "revenue_growth_3y": float(row.revenue_growth_3y or 0),
                    "earnings_growth_3y": float(row.earnings_growth_3y or 0),
                    "total_market_cap": float(row.total_market_cap or 0),
                }

                score = 50
                reasons = []

                if ratios["roe"] > 15:
                    score += 15
                    reasons.append(f"高ROE({ratios['roe']:.1f}%)")
                elif ratios["roe"] > 8:
                    score += 5

                if 0 < ratios["pe_ratio"] < 20:
                    score += 10
                    reasons.append(f"合理PE({ratios['pe_ratio']:.1f})")
                elif ratios["pe_ratio"] > 50:
                    score -= 10
                    reasons.append(f"高PE({ratios['pe_ratio']:.1f})")

                if ratios["debt_to_equity"] < 40:
                    score += 10
                    reasons.append("低杠杆")
                elif ratios["debt_to_equity"] > 100:
                    score -= 10
                    reasons.append("高杠杆")

                if ratios["revenue_growth_3y"] > 15:
                    score += 10
                    reasons.append("稳定增长")
                elif ratios["revenue_growth_3y"] < -10:
                    score -= 10
                    reasons.append("收入下滑")

                if ratios["gross_margin"] > 40:
                    score += 10
                    reasons.append("高毛利率")

                score = max(0, min(100, score))
                signal = "healthy" if score >= 60 else "caution" if score >= 35 else "risk"

                return {
                    "stock_code": stock_code,
                    "ratios": ratios,
                    "score": score,
                    "signal": signal,
                    "reasons": reasons,
                }
            finally:
                session.close()
        except Exception as e:
            return {"stock_code": stock_code, "error": str(e)[:120]}

    # ── 工具3: 技术形态分析 ──

    def technical_pattern(self, prices: list[float] | None = None) -> dict:
        """分析价格序列的技术形态

        Args:
            prices: 收盘价列表 (时间升序, 最近的在最后)

        Returns:
            {ma_alignment, trend, rsi, volatility, support_resistance}
        """
        if not prices or len(prices) < 5:
            return {"error": "insufficient data", "min_required": 5}

        try:
            n = len(prices)

            # 均线计算
            def ma(period: int) -> float:
                return sum(prices[-period:]) / period if n >= period else prices[-1]

            ma5 = ma(5)
            ma10 = ma(10) if n >= 10 else None
            ma20 = ma(20) if n >= 20 else None
            ma60 = ma(60) if n >= 60 else None

            # 均线排列
            ma_values = [(5, ma5)]
            if ma10 is not None:
                ma_values.append((10, ma10))
            if ma20 is not None:
                ma_values.append((20, ma20))
            if ma60 is not None:
                ma_values.append((60, ma60))

            sorted_ma = sorted(ma_values, key=lambda x: x[0])
            short_ma = sorted_ma[0][1]
            long_ma = sorted_ma[-1][1]

            if short_ma > long_ma * 1.02:
                ma_alignment = "bullish"
            elif short_ma < long_ma * 0.98:
                ma_alignment = "bearish"
            else:
                ma_alignment = "neutral"

            # 趋势强度 (价格 vs MA20)
            deviation = (prices[-1] - ma20) / ma20 * 100 if ma20 is not None else 0

            # RSI (14日)
            if n >= 15:
                gains: float = 0.0
                losses: float = 0.0
                for i in range(n - 14, n):
                    change = prices[i] - prices[i - 1]
                    if change > 0:
                        gains += change
                    else:
                        losses -= change
                avg_gain = gains / 14
                avg_loss = max(losses / 14, 0.001)
                rs = avg_gain / avg_loss
                rsi_val = 100 - (100 / (1 + rs))
            else:
                rsi_val = 50

            # 波动率 (20日)
            if n >= 21:
                returns = [
                    (prices[i] - prices[i - 1]) / prices[i - 1]
                    for i in range(n - 19, n)
                    if prices[i - 1] > 0
                ]
                vol = (sum(r * r for r in returns) / max(len(returns), 1)) ** 0.5 * 100
            else:
                vol = 0

            # 简单支撑阻力位
            recent = prices[-20:] if n >= 20 else prices
            support = min(recent[-5:])
            resistance = max(recent[-5:])

            return {
                "ma_alignment": ma_alignment,
                "deviation_pct": round(deviation, 2),
                "rsi": round(rsi_val, 1),
                "volatility": round(vol, 2),
                "current_price": prices[-1],
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2) if ma10 else None,
                "ma20": round(ma20, 2) if ma20 else None,
                "support": round(support, 2),
                "resistance": round(resistance, 2),
                "trend": "bullish" if deviation > 3 else "bearish" if deviation < -3 else "neutral",
            }
        except Exception as e:
            return {"error": str(e)[:120]}

    # ── 工具4: 风险扫描 ──

    def risk_scan(self, stock_code: str) -> dict:
        """扫描风险因素: 质押/减持/财务疑点

        Returns:
            {stock_code, risk_items: list[dict], risk_level, score}
        """
        risks = []
        score = 0  # 风险分, 越高越危险

        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            try:
                row = session.query(StockInfo).filter(StockInfo.stock_code == stock_code).first()
                if not row:
                    return {"stock_code": stock_code, "error": "not found", "risk_level": "unknown"}

                # 杠杆风险
                debt_eq = float(row.debt_to_equity or 0)
                if debt_eq > 150:
                    risks.append(
                        {
                            "type": "high_leverage",
                            "severity": "high",
                            "detail": f"资产负债率过高({debt_eq:.0f}%)",
                        }
                    )
                    score += 30
                elif debt_eq > 80:
                    risks.append(
                        {
                            "type": "high_leverage",
                            "severity": "medium",
                            "detail": f"负债率偏高({debt_eq:.0f}%)",
                        }
                    )
                    score += 15

                # 估值风险
                pe = float(row.pe_ratio or 0)
                if pe > 100:
                    risks.append(
                        {
                            "type": "valuation_bubble",
                            "severity": "high",
                            "detail": f"PE过高({pe:.1f})",
                        }
                    )
                    score += 20
                elif pe > 50:
                    risks.append(
                        {
                            "type": "valuation_bubble",
                            "severity": "medium",
                            "detail": f"PE较高({pe:.1f})",
                        }
                    )
                    score += 10

                # 流动性风险
                turnover = float(row.turnover_rate or 0)
                if turnover < 0.5:
                    risks.append(
                        {
                            "type": "low_liquidity",
                            "severity": "medium",
                            "detail": f"换手率过低({turnover:.2f}%)",
                        }
                    )
                    score += 10

                # 盈利风险
                eps = float(row.eps or 0)
                if eps <= 0:
                    risks.append(
                        {"type": "negative_earnings", "severity": "high", "detail": "每股收益为负"}
                    )
                    score += 25

                # 增长风险
                revenue_growth = float(row.revenue_growth_3y or 0)
                if revenue_growth < -20:
                    risks.append(
                        {
                            "type": "revenue_decline",
                            "severity": "high",
                            "detail": f"营收大幅下滑({revenue_growth:.0f}%)",
                        }
                    )
                    score += 20
                elif revenue_growth < -5:
                    risks.append(
                        {
                            "type": "revenue_decline",
                            "severity": "low",
                            "detail": f"营收下滑({revenue_growth:.0f}%)",
                        }
                    )
                    score += 5

                risk_level = "high" if score >= 50 else "medium" if score >= 20 else "low"

                return {
                    "stock_code": stock_code,
                    "risk_items": risks,
                    "risk_score": score,
                    "risk_level": risk_level,
                }
            finally:
                session.close()
        except Exception as e:
            return {"stock_code": stock_code, "error": str(e)[:120], "risk_level": "unknown"}

    # ── 工具5: 相对强度 ──

    def relative_strength(self, stock_code: str) -> dict:
        """计算股票相对强度 (与板块/全市场对比)

        Returns:
            {stock_code, industry, rs_score, vs_industry, vs_market}
        """
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            try:
                row = session.query(StockInfo).filter(StockInfo.stock_code == stock_code).first()
                if not row:
                    return {"stock_code": stock_code, "error": "not found"}

                # 当前股票数据
                stock_change = float(row.change_pct or 0)
                industry = row.industry or "未知"

                # 同行业对比
                industry_stocks = (
                    session.query(StockInfo)
                    .filter(
                        StockInfo.industry == industry,
                        StockInfo.change_pct.isnot(None),
                        StockInfo.latest_price > 0,
                    )
                    .all()
                )

                if industry_stocks:
                    industry_changes = [float(s.change_pct or 0) for s in industry_stocks]
                    industry_avg = sum(industry_changes) / len(industry_changes)
                    industry_max = max(industry_changes)
                    industry_min = min(industry_changes)
                    rank_in_industry = sum(1 for c in industry_changes if c > stock_change)
                    industry_percentile = rank_in_industry / len(industry_changes) * 100
                else:
                    industry_avg = 0
                    industry_max = 0
                    industry_min = 0
                    industry_percentile = 50

                # 全市场对比
                all_stocks = (
                    session.query(StockInfo)
                    .filter(
                        StockInfo.change_pct.isnot(None),
                        StockInfo.latest_price > 0,
                    )
                    .all()
                )
                if all_stocks:
                    all_changes = [float(s.change_pct or 0) for s in all_stocks]
                    market_avg = sum(all_changes) / len(all_changes)
                    rank_all = sum(1 for c in all_changes if c > stock_change)
                    market_percentile = rank_all / len(all_changes) * 100
                else:
                    market_avg = 0
                    market_percentile = 50

                # RS评分: 0-100, 越高越强
                rs_score = industry_percentile * 0.6 + market_percentile * 0.4

                return {
                    "stock_code": stock_code,
                    "industry": industry,
                    "rs_score": round(rs_score, 1),
                    "stock_change_pct": stock_change,
                    "industry_avg_change": round(industry_avg, 2),
                    "industry_max_change": round(industry_max, 2),
                    "industry_min_change": round(industry_min, 2),
                    "industry_percentile": round(industry_percentile, 1),
                    "market_percentile": round(market_percentile, 1),
                    "vs_industry": "outperform" if stock_change > industry_avg else "underperform",
                    "vs_market": "outperform" if stock_change > market_avg else "underperform",
                }
            finally:
                session.close()
        except Exception as e:
            return {"stock_code": stock_code, "error": str(e)[:120]}
