"""Test trend analyzer — pure NumPy technical indicators"""

from services.trend_analyzer import TrendAnalyzer, ma, macd, macd_status, rsi, trend_strength


class TestMa:
    def test_basic(self):
        result = ma([1, 2, 3, 4, 5], 3)
        assert result[-1] == 4.0

    def test_short_window(self):
        result = ma([1, 2], 3)
        assert len(result) == 2


class TestRsi:
    def test_oversold(self):
        prices = [100] + [95 - i for i in range(14)]
        assert rsi(prices, 14) < 30

    def test_overbought(self):
        prices = [100] + [105 + i for i in range(14)]
        assert rsi(prices, 14) > 70

    def test_short_data(self):
        assert rsi([10], 14) == 50.0


class TestMacd:
    def test_basic(self):
        prices = list(range(30))
        result = macd(prices)
        assert "dif" in result
        assert "dea" in result
        assert "bar" in result

    def test_short_data(self):
        result = macd([1, 2, 3])
        assert result["dif"] == 0.0


class TestMacdStatus:
    def test_golden_cross_zero(self):
        assert macd_status(0.5, 0.3, -0.1, 0.0) == "GOLDEN_CROSS_ZERO"

    def test_golden_cross(self):
        assert macd_status(0.5, 0.3, 0.4, 0.45) == "GOLDEN_CROSS_ZERO"


class TestTrendStrength:
    def test_uptrend(self):
        prices = [10 + i * 0.2 for i in range(30)]
        result = trend_strength(prices)
        assert result > 50

    def test_short_data(self):
        assert trend_strength([1, 2, 3]) == 0.0


class TestTrendAnalyzer:
    def test_uptrend_detected(self):
        prices = [10 + i * 0.2 for i in range(60)]
        volumes = [1000000 + i * 1000 for i in range(60)]
        result = TrendAnalyzer.analyze(prices, volumes)
        assert result["valid"]
        assert result["ma_uptrend"]
        assert result["trend_strength"] > 50

    def test_too_short_returns_invalid(self):
        result = TrendAnalyzer.analyze([10, 11], [100, 200])
        assert not result["valid"]

    def test_result_has_all_keys(self):
        prices = [10 + i * 0.1 for i in range(60)]
        volumes = [1000000 for _ in range(60)]
        result = TrendAnalyzer.analyze(prices, volumes)
        assert result["valid"]
        for key in [
            "ma5",
            "ma10",
            "ma20",
            "bias_ma5",
            "rsi_12",
            "macd",
            "macd_status",
            "trend_strength",
            "daily_volume_ratio",
            "ma_uptrend",
        ]:
            assert key in result, f"Missing key: {key}"
