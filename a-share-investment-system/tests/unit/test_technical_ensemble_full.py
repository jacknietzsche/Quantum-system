"""Tests for services/technical_ensemble.py"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _make_df(n=60):
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n)
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    high = close + abs(np.random.randn(n))
    low = close - abs(np.random.randn(n))
    vol = np.random.randint(1000, 10000, n).astype(float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


class TestTechnicalHelpers:
    def test_safe_float_normal(self):
        from services.technical_ensemble import safe_float

        assert safe_float(3.14) == 3.14
        assert safe_float("abc", 1.0) == 1.0

    def test_safe_float_nan(self):
        from services.technical_ensemble import safe_float

        assert safe_float(float("nan")) == 0.0

    def test_calculate_rsi(self):
        from services.technical_ensemble import calculate_rsi

        df = _make_df(60)
        rsi = calculate_rsi(df)
        assert len(rsi) == 60

    def test_calculate_ema(self):
        from services.technical_ensemble import calculate_ema

        df = _make_df(60)
        ema = calculate_ema(df, 12)
        assert len(ema) == 60

    def test_calculate_bollinger(self):
        from services.technical_ensemble import calculate_bollinger_bands

        df = _make_df(60)
        upper, lower = calculate_bollinger_bands(df)
        assert len(upper) == 60

    def test_calculate_adx(self):
        from services.technical_ensemble import calculate_adx

        df = _make_df(60)
        result = calculate_adx(df)
        assert len(result) == 60

    def test_calculate_atr(self):
        from services.technical_ensemble import calculate_atr

        df = _make_df(60)
        result = calculate_atr(df)
        assert len(result) == 60

    def test_calculate_hurst(self):
        from services.technical_ensemble import calculate_hurst_exponent

        prices = pd.Series(100 + np.cumsum(np.random.randn(100) * 2))
        result = calculate_hurst_exponent(prices)
        assert isinstance(result, float)

    def test_weighted_signal(self):
        from services.technical_ensemble import weighted_signal_combination

        signals = {"macd": {"signal": "buy", "score": 70}, "rsi": {"signal": "hold", "score": 30}}
        weights = {"macd": 0.6, "rsi": 0.4}
        result = weighted_signal_combination(signals, weights)
        assert isinstance(result, dict)


class TestTechnicalEnsemble:
    def test_analyze(self):
        from services.technical_ensemble import TechnicalEnsemble

        te = TechnicalEnsemble()
        df = _make_df(60)
        result = te.analyze(df)
        assert hasattr(result, "data") or isinstance(result, dict)

    def test_get_metrics(self):
        from services.technical_ensemble import TechnicalEnsemble

        te = TechnicalEnsemble()
        metrics = te.get_metrics()
        assert isinstance(metrics, dict)

    def test_health_check(self):
        from services.technical_ensemble import TechnicalEnsemble

        te = TechnicalEnsemble()
        result = te.health_check()
        assert isinstance(result, bool)
