"""5维市场环境感知服务 - 来源: QuantLLM"""

from typing import ClassVar

from services.base import BaseService, ServiceResult


class MarketPerception(BaseService):
    """5维度融合市场环境感知"""

    # 维度权重(来源: QuantLLM IC分析)
    DIMENSION_WEIGHTS: ClassVar[dict[str, float]] = {
        "trend_position": 0.25,
        "trend_direction": 0.25,
        "volume_confirm": 0.15,
        "volatility": 0.15,
        "price_momentum": 0.20,
    }

    def perceive(self, market_data: dict) -> ServiceResult:
        """输入原始市场数据,输出完整环境感知"""
        try:
            breadth = market_data.get("breadth", {})
            indices = market_data.get("indices", {})

            scores = self._score_dimensions(breadth, indices)
            total = sum(s * self.DIMENSION_WEIGHTS[k] for k, s in scores.items())

            regime = self._classify(total, breadth)
            adaptive = self._adaptive_params(regime)
            phase = self._detect_trading_phase()

            return ServiceResult.ok(
                data={
                    "regime": regime,
                    "total_score": round(total, 2),
                    "dimension_scores": scores,
                    "adaptive_params": adaptive,
                    "trading_phase": phase,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"MarketPerception failed: {e}"])

    def _score_dimensions(self, breadth: dict, indices: dict) -> dict[str, float]:
        """计算5维度独立评分(范围: -2 ~ +2)"""
        up = breadth.get("up", 0)
        down = breadth.get("down", 0)
        total = breadth.get("total", 1)
        limit_down = breadth.get("limit_down", 0)
        limit_up = breadth.get("limit_up", 0)

        if total > 0:
            up_ratio = up / total
            if up_ratio > 0.7:
                d1_score = min(2.0, (up_ratio - 0.5) * 5)
            elif up_ratio < 0.3:
                d1_score = max(-2.0, (up_ratio - 0.5) * 5)
            else:
                d1_score = (up_ratio - 0.5) * 4
        else:
            d1_score = 0.0

        if total > 0:
            imbalance = (up - down) / total
            d2_score = max(-2.0, min(2.0, imbalance * 3))
        else:
            d2_score = 0.0

        # D3: 量能确认 - 涨停数 vs 跌停数 (范围: -2 ~ +2)
        if limit_up + limit_down > 0:
            d3_score = max(-2.0, min(2.0, (limit_up - limit_down) / max(total, 1) * 20))
        else:
            d3_score = 0.0

        # D4: 波动率 - 跌停占比反映恐慌程度 (范围: -2 ~ +2)
        if total > 0:
            limit_down_ratio = limit_down / total
            limit_up_ratio = limit_up / total
            if limit_down_ratio > 0.10:
                d4_score = -2.0
            elif limit_down_ratio > 0.05:
                d4_score = -1.5
            elif limit_down_ratio > 0.02:
                d4_score = -0.8
            elif limit_up_ratio > 0.15:
                d4_score = 2.0
            elif limit_up_ratio > 0.10:
                d4_score = 1.0
            elif limit_up_ratio > 0.05:
                d4_score = 0.5
            else:
                d4_score = 0.0
        else:
            d4_score = 0.0

        # D5: 价格动量 - 从广度数据推断 (范围: -2 ~ +2)
        if total > 0:
            up_ratio = up / total
            if up_ratio > 0.85:
                d5_score = 2.0
            elif up_ratio > 0.75:
                d5_score = 1.5
            elif up_ratio > 0.65:
                d5_score = 1.0
            elif up_ratio < 0.15:
                d5_score = -2.0
            elif up_ratio < 0.25:
                d5_score = -1.5
            elif up_ratio < 0.35:
                d5_score = -1.0
            else:
                d5_score = 0.0
        else:
            d5_score = 0.0

        return {
            "trend_position": round(d1_score, 1),
            "trend_direction": round(d2_score, 1),
            "volume_confirm": round(d3_score, 1),
            "volatility": round(d4_score, 1),
            "price_momentum": round(d5_score, 1),
        }

    def _classify(self, total: float, breadth: dict) -> str:
        """环境分类"""
        limit_down = breadth.get("limit_down", 0)
        limit_up = breadth.get("limit_up", 0)
        total_stocks = breadth.get("total", 1)

        # 阈值校准(总分范围[-2.0, +2.0],实际交易日通常±1.5以内)
        if limit_down > 50 and total < -1.0:
            return "PANIC"
        if limit_up > 150 and total_stocks > 0 and limit_up / total_stocks > 0.03:
            return "OVERHEAT"

        if total >= 1.0:
            return "BULL"
        if total <= -1.0:
            return "BEAR"
        return "NEUTRAL"

    def _adaptive_params(self, regime: str) -> dict:
        """自适应参数映射"""
        params = {
            "BULL": {
                "target_position_pct": 0.95,
                "max_holdings": 10,
                "selection_threshold": "buy+strong_buy",
            },
            "NEUTRAL": {
                "target_position_pct": 0.50,
                "max_holdings": 5,
                "selection_threshold": "buy+strong_buy",
            },
            "BEAR": {
                "target_position_pct": 0.30,
                "max_holdings": 3,
                "selection_threshold": "strong_buy_only",
            },
            "PANIC": {
                "target_position_pct": 0.10,
                "max_holdings": 1,
                "selection_threshold": "strong_buy_only",
            },
            "OVERHEAT": {
                "target_position_pct": 0.70,
                "max_holdings": 8,
                "selection_threshold": "buy+strong_buy",
            },
        }
        return params.get(regime, params["NEUTRAL"])

    def _detect_trading_phase(self) -> str:
        """检测当前交易阶段"""
        from datetime import datetime

        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        weekday = now.weekday()

        if weekday >= 5:
            return "holiday"
        if hour < 9.5:
            return "pre_market"
        if 9.5 <= hour <= 11.5:
            return "intraday_morning"
        if 11.5 < hour < 13.0:
            return "lunch_break"
        if 13.0 <= hour <= 15.0:
            return "intraday_afternoon"
        return "post_market"

    def get_position_limits(self) -> ServiceResult:
        return ServiceResult.ok(data={"message": "Call perceive() first to get adaptive_params"})

    def is_trading_day(self, date: str | None = None) -> bool:
        """判断是否为A股交易日(简化版:仅排除周末)"""
        from datetime import datetime

        target = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        return target.weekday() < 5
