"""单元测试 — 技术指标计算库"""

import numpy as np
import pandas as pd

from shared.indicators import (
    classify_ma_alignment,
    classify_trend,
    compute_all_indicators,
    compute_all_ma,
    compute_ma,
    compute_max_drawdown,
    compute_rsi,
    compute_volatility,
)


def _rising_series(n=30):
    """单调上升的价格序列"""
    return pd.Series(range(100, 100 + n))


def _falling_series(n=30):
    """单调下降的价格序列"""
    return pd.Series(range(100 + n, 100, -1))


def _volatile_series(n=30):
    """震荡价格序列"""
    return pd.Series(100 + np.sin(np.linspace(0, 4 * np.pi, n)) * 10)


class TestMA:
    def test_compute_ma5(self):
        close = _rising_series(10)
        ma = compute_ma(close, 5)
        assert 100 < ma < 110

    def test_compute_all_ma(self):
        close = _rising_series(100)
        mas = compute_all_ma(close)
        assert "ma5" in mas and "ma10" in mas
        assert all(mas[k] > 100 for k in mas)


class TestRSI:
    def test_rsi_rising(self):
        R"""上升趋势的RSI应 > 50"""
        np.random.seed(42)
        trend = np.linspace(0, 20, 30)
        noise = np.random.randn(30) * 0.5
        close = pd.Series(100 + trend + noise)
        rsi = compute_rsi(close)
        assert rsi >= 50  # 上升趋势RSI应不低于50

    def test_rsi_falling(self):
        R"""下降趋势的RSI应 < 50"""
        np.random.seed(42)
        trend = np.linspace(0, -20, 30)
        noise = np.random.randn(30) * 0.5
        close = pd.Series(100 + trend + noise)
        rsi = compute_rsi(close)
        assert rsi <= 50  # 下降趋势RSI应不高于50


class TestTrend:
    def test_uptrend(self):
        assert classify_trend(15, 12, 10) == "上升"

    def test_downtrend(self):
        assert classify_trend(10, 12, 15) == "下降"

    def test_sideways(self):
        assert classify_trend(12, 12, 12) == "震荡"


class TestAlignment:
    def test_bullish(self):
        assert classify_ma_alignment(15, 13, 11, 9) == "多头"

    def test_bearish(self):
        assert classify_ma_alignment(9, 11, 13, 15) == "空头"

    def test_crossover(self):
        assert classify_ma_alignment(12, 12, 12, 12) == "交叉"


class TestComputeAll:
    def test_all_indicators_return_all_keys(self):
        close = _volatile_series(100)
        result = compute_all_indicators(close)
        expected_keys = {
            "ma5",
            "ma10",
            "ma20",
            "ma60",
            "rsi_14",
            "volatility_20d",
            "max_drawdown_60d",
            "trend",
            "ma_alignment",
        }
        assert expected_keys.issubset(result.keys())

    def test_indicators_with_short_data(self):
        close = _rising_series(10)
        result = compute_all_indicators(close)
        assert result["ma60"] is not None  # short data fallback works


class TestVolatility:
    def test_volatility_non_negative(self):
        close = _volatile_series(60)
        vol = compute_volatility(close)
        assert vol >= 0

    def test_max_drawdown_non_positive(self):
        close = _rising_series(60)
        dd = compute_max_drawdown(close)
        assert dd <= 0  # 上升序列最大回撤为0或负
