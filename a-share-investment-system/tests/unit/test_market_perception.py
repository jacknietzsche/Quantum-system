"""MarketPerception 单元测试 — 5维市场感知评分"""

from services.market_perception import MarketPerception


class TestMarketPerception:
    def setup_method(self):
        self.mp = MarketPerception()

    def test_perceive_returns_ok(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 2500,
                    "down": 2000,
                    "total": 5000,
                    "limit_up": 30,
                    "limit_down": 10,
                },
                "indices": {},
            }
        )
        assert result.status == "ok"

    def test_perceive_has_regime(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 2500,
                    "down": 2000,
                    "total": 5000,
                    "limit_up": 30,
                    "limit_down": 10,
                },
                "indices": {},
            }
        )
        assert "regime" in result.data
        assert result.data["regime"] in ("BULL", "BEAR", "NEUTRAL", "EXTREME_FEAR", "EXTREME_GREED")

    def test_perceive_has_total_score(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 2500,
                    "down": 2000,
                    "total": 5000,
                    "limit_up": 30,
                    "limit_down": 10,
                },
                "indices": {},
            }
        )
        assert "total_score" in result.data
        assert isinstance(result.data["total_score"], (int, float))

    def test_perceive_has_adaptive_params(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 2500,
                    "down": 2000,
                    "total": 5000,
                    "limit_up": 30,
                    "limit_down": 10,
                },
                "indices": {},
            }
        )
        assert "adaptive_params" in result.data
        assert "target_position_pct" in result.data["adaptive_params"]

    def test_perceive_has_dimension_scores(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 2500,
                    "down": 2000,
                    "total": 5000,
                    "limit_up": 30,
                    "limit_down": 10,
                },
                "indices": {},
            }
        )
        scores = result.data["dimension_scores"]
        assert "trend_position" in scores
        assert "trend_direction" in scores
        assert "volume_confirm" in scores
        assert "volatility" in scores
        assert "price_momentum" in scores

    def test_bullish_breadth_gives_high_score(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 4000,
                    "down": 500,
                    "total": 5000,
                    "limit_up": 100,
                    "limit_down": 5,
                },
                "indices": {},
            }
        )
        assert result.data["total_score"] > 0

    def test_bearish_breadth_gives_low_score(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 500,
                    "down": 4000,
                    "total": 5000,
                    "limit_up": 5,
                    "limit_down": 100,
                },
                "indices": {},
            }
        )
        assert result.data["total_score"] < 0

    def test_neutral_breadth_gives_neutral_score(self):
        result = self.mp.perceive(
            {
                "breadth": {
                    "up": 2500,
                    "down": 2500,
                    "total": 5000,
                    "limit_up": 10,
                    "limit_down": 10,
                },
                "indices": {},
            }
        )
        assert -1.0 < result.data["total_score"] < 1.0

    def test_empty_breadth_handles_gracefully(self):
        result = self.mp.perceive({"breadth": {}, "indices": {}})
        assert result.status == "ok"

    def test_empty_data_handles_gracefully(self):
        result = self.mp.perceive({})
        assert result.status == "ok"

    def test_dimension_weights_sum_to_one(self):
        total = sum(MarketPerception.DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01
