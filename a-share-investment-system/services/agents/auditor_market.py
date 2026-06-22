"""AuditorMarket - 市场微观结构师: 验证价格行为是否支持量化信号"""

import logging

logger = logging.getLogger(__name__)


class AuditorMarket:
    """市场微观结构审计 - 纯规则引擎, 验证价格行为"""

    def audit(self, stock_code: str, technical: dict, sentiment: dict | None = None) -> dict:
        """执行市场微观结构审计"""
        tech_confirmation = 50  # 中性基准
        divergence_signals = []
        volume_support = False

        # 1. 量价关系
        volume_ratio = technical.get("volume_ratio", 0)
        if volume_ratio > 1.5:
            tech_confirmation += 15
            volume_support = True
        elif volume_ratio < 0.5:
            tech_confirmation -= 10
            divergence_signals.append("volume_shrinking")

        # 2. 均线排列
        ma5 = technical.get("ma5", 0)
        ma10 = technical.get("ma10", 0)
        ma20 = technical.get("ma20", 0)
        price = technical.get("price", 0)
        if ma5 > ma10 > ma20 and price > ma5:
            tech_confirmation += 15
        elif ma5 < ma10 and price < ma20:
            tech_confirmation -= 10
            divergence_signals.append("ma_bearish_cross")

        # 3. 波动率
        volatility = technical.get("volatility_20d", 0)
        if volatility and volatility < 30:
            tech_confirmation += 5
        elif volatility and volatility > 50:
            tech_confirmation -= 5
            divergence_signals.append("high_volatility")

        # 4. 趋势强度
        trend = technical.get("trend", "")
        if trend == "up":
            tech_confirmation += 10
        elif trend == "down":
            tech_confirmation -= 10
            divergence_signals.append("downtrend")

        # 5. 龙虎榜资金流向
        if sentiment:
            lhb_net = sentiment.get("lhb_net_buy", 0)
            if lhb_net and lhb_net > 10_000_000:
                tech_confirmation += 10
                volume_support = True
            elif lhb_net and lhb_net < -10_000_000:
                tech_confirmation -= 8
                divergence_signals.append("lhb_net_outflow")

        return {
            "tech_confirmation_score": max(0, min(100, tech_confirmation)),
            "volume_support": volume_support,
            "divergence_signals": divergence_signals,
            "confidence": 0.8,
        }
