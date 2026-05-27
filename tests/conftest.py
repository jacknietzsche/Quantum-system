"""共享 fixtures — 量化系统测试"""
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """项目根目录"""
    from core.config import PROJECT_ROOT
    return PROJECT_ROOT


@pytest.fixture
def db_path(project_root):
    """本地数据库路径"""
    return project_root / "local_db" / "a_stock_quant.db"


@pytest.fixture
def sample_stock_code():
    """样例股票代码（贵州茅台）"""
    return "600519"


@pytest.fixture
def sample_daily_df():
    """样例日线 DataFrame（合成数据）"""
    import pandas as pd
    import numpy as np

    np.random.seed(42)
    n = 120
    dates = pd.bdate_range("2025-01-01", periods=n)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    opn = close + np.random.randn(n) * 0.2
    volume = np.random.randint(1_000_000, 50_000_000, size=n).astype(float)

    return pd.DataFrame({
        "trade_date": dates.strftime("%Y-%m-%d"),
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": volume * close,
        "turnover": np.random.rand(n) * 5,
        "pct_chg": np.concatenate([[0], np.diff(close) / close[:-1] * 100]),
    })
