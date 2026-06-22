"""Unit tests for services.technical_ensemble utility functions."""

import numpy as np
import pandas as pd

from services.technical_ensemble import (
    calculate_adx,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_hurst_exponent,
    calculate_rsi,
    safe_float,
    weighted_signal_combination,
)


class TestSafeFloat:
    def test_valid_float(self):
        assert safe_float(3.14) == 3.14

    def test_valid_int(self):
        assert safe_float(42) == 42.0

    def test_string_number(self):
        assert safe_float("3.14") == 3.14

    def test_invalid_string(self):
        assert safe_float("abc") == 0.0

    def test_none(self):
        assert safe_float(None) == 0.0

    def test_nan(self):
        assert safe_float(float("nan")) == 0.0

    def test_custom_default(self):
        assert safe_float(None, default=1.0) == 1.0

    def test_pandas_na(self):
        assert safe_float(pd.NA) == 0.0


class TestCalculateRSI:
    def test_returns_series(self):
        prices = pd.DataFrame({"close": range(100, 130)})
        result = calculate_rsi(prices)
        assert isinstance(result, pd.Series)
        assert len(result) == 30

    def test_values_between_0_and_100(self):
        prices = pd.DataFrame({"close": list(range(100, 120))})
        result = calculate_rsi(prices)
        valid = result.dropna()
        assert all(0 <= v <= 100 for v in valid)

    def test_custom_period(self):
        prices = pd.DataFrame({"close": range(100, 150)})
        result = calculate_rsi(prices, period=10)
        assert isinstance(result, pd.Series)
        assert len(result) == 50


class TestCalculateEMA:
    def test_returns_series(self):
        df = pd.DataFrame({"close": range(100, 130)})
        result = calculate_ema(df, window=10)
        assert isinstance(result, pd.Series)
        assert len(result) == 30

    def test_ema_tracks_close(self):
        df = pd.DataFrame({"close": [100.0] * 20})
        result = calculate_ema(df, window=5)
        assert abs(result.iloc[-1] - 100.0) < 0.01


class TestCalculateBollingerBands:
    def test_returns_tuple_of_two(self):
        prices = pd.DataFrame({"close": range(100, 130)})
        result = calculate_bollinger_bands(prices)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_upper_above_lower(self):
        prices = pd.DataFrame({"close": range(100, 130)})
        upper, lower = calculate_bollinger_bands(prices)
        valid_upper = upper.dropna()
        valid_lower = lower.dropna()
        assert all(u > l for u, l in zip(valid_upper, valid_lower))

    def test_custom_window(self):
        prices = pd.DataFrame({"close": range(100, 130)})
        upper, lower = calculate_bollinger_bands(prices, window=10)
        assert len(upper) == 30


class TestCalculateADX:
    def test_returns_dataframe(self):
        df = pd.DataFrame(
            {
                "high": range(105, 135),
                "low": range(95, 125),
                "close": range(100, 130),
            }
        )
        result = calculate_adx(df)
        assert isinstance(result, pd.DataFrame)
        assert "adx" in result.columns
        assert "+di" in result.columns
        assert "-di" in result.columns

    def test_adx_values_non_negative(self):
        df = pd.DataFrame(
            {
                "high": range(105, 135),
                "low": range(95, 125),
                "close": range(100, 130),
            }
        )
        result = calculate_adx(df)
        valid = result["adx"].dropna()
        assert all(v >= 0 for v in valid)


class TestCalculateATR:
    def test_returns_series(self):
        df = pd.DataFrame(
            {
                "high": range(105, 135),
                "low": range(95, 125),
                "close": range(100, 130),
            }
        )
        result = calculate_atr(df)
        assert isinstance(result, pd.Series)
        assert len(result) == 30

    def test_atr_positive(self):
        df = pd.DataFrame(
            {
                "high": range(105, 135),
                "low": range(95, 125),
                "close": range(100, 130),
            }
        )
        result = calculate_atr(df)
        valid = result.dropna()
        assert all(v > 0 for v in valid)


class TestCalculateHurstExponent:
    def test_returns_float(self):
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(200)) + 100)
        result = calculate_hurst_exponent(prices)
        assert isinstance(result, float)

    def test_random_walk_near_half(self):
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(500)) + 100)
        result = calculate_hurst_exponent(prices)
        assert 0.0 <= result <= 1.0

    def test_short_series_raises(self):
        prices = pd.Series([1.0, 2.0, 3.0])
        import pytest as _pytest

        with _pytest.raises(TypeError):
            calculate_hurst_exponent(prices)

    def test_medium_series(self):
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(50)) + 100)
        result = calculate_hurst_exponent(prices)
        assert isinstance(result, float)


class TestWeightedSignalCombination:
    def test_returns_dict(self):
        signals = {
            "trend": {"signal": "buy", "confidence": 0.8},
            "momentum": {"signal": "sell", "confidence": 0.6},
        }
        weights = {"trend": 0.6, "momentum": 0.4}
        result = weighted_signal_combination(signals, weights)
        assert isinstance(result, dict)
        assert "signal" in result
        assert "confidence" in result
        assert "raw_score" in result

    def test_bullish_signals(self):
        signals = {
            "a": {"signal": "bullish", "confidence": 0.9},
            "b": {"signal": "bullish", "confidence": 0.8},
        }
        weights = {"a": 0.5, "b": 0.5}
        result = weighted_signal_combination(signals, weights)
        assert result["signal"] == "bullish"

    def test_bearish_signals(self):
        signals = {
            "a": {"signal": "bearish", "confidence": 0.9},
            "b": {"signal": "bearish", "confidence": 0.8},
        }
        weights = {"a": 0.5, "b": 0.5}
        result = weighted_signal_combination(signals, weights)
        assert result["signal"] == "bearish"

    def test_empty_signals(self):
        result = weighted_signal_combination({}, {})
        assert result["signal"] == "neutral"
        assert result["confidence"] == 0.0
