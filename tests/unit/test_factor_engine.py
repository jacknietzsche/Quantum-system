"""FactorEngineV2 单元测试（合成数据）"""
import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 200
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = 50 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1.0)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    low = np.maximum(low, 0.5)
    volume = np.random.randint(1_000_000, 50_000_000, size=n).astype(float)
    return pd.DataFrame({
        "trade_date": dates,
        "open": close + np.random.randn(n) * 0.1,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": volume * close,
        "turnover": np.random.rand(n) * 5,
        "pct_chg": np.concatenate([[0], np.diff(close) / close[:-1] * 100]),
    })


def test_factor_engine_init():
    from core.factor_engine_v2 import FactorEngineV2
    engine = FactorEngineV2()
    assert engine is not None


def test_factor_engine_calculate(sample_df):
    from core.factor_engine_v2 import FactorEngineV2
    engine = FactorEngineV2()
    result = engine.calculate(sample_df)
    assert isinstance(result, dict)
    assert "adjustment_coef" in result
