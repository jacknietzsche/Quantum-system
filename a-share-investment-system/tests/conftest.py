"""测试共享 fixtures 与配置。"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

# 将被测代码目录加入 Python 路径
_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)


# ── 模拟行情数据 ──────────────────────────────────────


@pytest.fixture
def mock_spot_data() -> pd.DataFrame:
    """模拟全市场实时行情(10只股票)。"""
    return pd.DataFrame(
        {
            "代码": [
                "600519",
                "000858",
                "300750",
                "600036",
                "601318",
                "002594",
                "688981",
                "000001",
                "600900",
                "000568",
            ],
            "名称": [
                "贵州茅台",
                "五粮液",
                "宁德时代",
                "招商银行",
                "中国平安",
                "比亚迪",
                "中芯国际",
                "平安银行",
                "长江电力",
                "泸州老窖",
            ],
            "最新价": [
                1800.50,
                150.00,
                210.00,
                42.30,
                55.80,
                280.00,
                85.00,
                13.50,
                25.20,
                220.00,
            ],
            "涨跌幅": [
                2.50,
                -1.20,
                0.80,
                -0.30,
                1.50,
                3.20,
                -2.10,
                0.10,
                -0.50,
                1.80,
            ],
            "涨跌额": [
                44.00,
                -1.82,
                1.67,
                -0.13,
                0.82,
                8.68,
                -1.82,
                0.01,
                -0.13,
                3.89,
            ],
            "成交量": [
                5000000,
                12000000,
                8000000,
                25000000,
                15000000,
                6000000,
                9000000,
                30000000,
                10000000,
                4000000,
            ],
            "成交额": [
                9.0e9,
                1.8e9,
                1.68e9,
                1.06e9,
                0.84e9,
                1.68e9,
                0.77e9,
                0.41e9,
                0.25e9,
                0.88e9,
            ],
            "最高": [
                1815.00,
                152.00,
                212.00,
                42.80,
                56.50,
                285.00,
                87.00,
                13.65,
                25.40,
                224.00,
            ],
            "最低": [
                1790.00,
                148.50,
                208.00,
                41.80,
                55.00,
                276.00,
                83.50,
                13.30,
                25.00,
                218.00,
            ],
            "今开": [
                1795.00,
                151.50,
                210.50,
                42.50,
                55.20,
                278.00,
                86.00,
                13.45,
                25.30,
                221.00,
            ],
            "昨收": [
                1756.50,
                151.82,
                208.33,
                42.43,
                54.98,
                271.32,
                86.82,
                13.49,
                25.33,
                216.11,
            ],
            "换手率": [
                0.40,
                0.80,
                1.20,
                0.50,
                0.60,
                1.00,
                1.50,
                2.00,
                0.30,
                0.70,
            ],
            "市盈率-动态": [
                35.0,
                25.0,
                45.0,
                8.0,
                12.0,
                40.0,
                60.0,
                6.0,
                18.0,
                30.0,
            ],
            "市净率": [
                12.0,
                5.0,
                8.0,
                1.2,
                1.5,
                6.0,
                3.0,
                0.9,
                2.5,
                7.0,
            ],
            "总市值": [
                2.26e12,
                5.8e11,
                9.2e11,
                1.1e12,
                7.8e11,
                8.5e11,
                4.5e11,
                3.0e11,
                5.5e11,
                3.2e11,
            ],
        }
    )


@pytest.fixture
def mock_history_data() -> pd.DataFrame:
    """模拟个股60日历史日K线。"""
    dates = pd.date_range(end=pd.Timestamp.today(), periods=60, freq="B")
    np.random.seed(42)
    base_price = 100.0
    returns = np.random.normal(0.0005, 0.015, 60)
    close_prices = base_price * (1 + returns).cumprod()

    return pd.DataFrame(
        {
            "日期": dates.strftime("%Y-%m-%d"),
            "开盘": close_prices * (1 + np.random.uniform(-0.01, 0.01, 60)),
            "收盘": close_prices,
            "最高": close_prices * (1 + np.abs(np.random.normal(0, 0.01, 60))),
            "最低": close_prices * (1 - np.abs(np.random.normal(0, 0.01, 60))),
            "成交量": np.random.randint(5000000, 30000000, 60),
            "成交额": close_prices * np.random.randint(5000000, 30000000, 60),
            "涨跌幅": np.append([0], np.diff(close_prices) / close_prices[:-1] * 100),
        }
    )


@pytest.fixture
def mock_index_data() -> pd.DataFrame:
    """模拟三大指数数据。"""
    return pd.DataFrame(
        {
            "代码": ["000001", "399001", "399006"],
            "名称": ["上证指数", "深证成指", "创业板指"],
            "最新价": [3200.50, 10800.00, 2200.00],
            "涨跌幅": [0.80, 1.20, 0.50],
            "涨跌额": [25.60, 128.00, 10.80],
            "成交量": [2.5e8, 1.8e8, 8.0e7],
            "成交额": [3.2e11, 2.5e11, 1.5e11],
        }
    )


@pytest.fixture
def sample_portfolio() -> list:
    """模拟持仓列表。"""
    return [
        {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "buy_date": "2025-01-15",
            "buy_price": 1700.00,
            "current_price": 1800.50,
            "quantity": 100,
            "current_value": 180050.00,
            "cost_value": 170000.00,
            "profit_loss": 10050.00,
            "profit_loss_pct": 5.91,
        },
        {
            "stock_code": "000858",
            "stock_name": "五粮液",
            "buy_date": "2025-03-01",
            "buy_price": 155.00,
            "current_price": 150.00,
            "quantity": 500,
            "current_value": 75000.00,
            "cost_value": 77500.00,
            "profit_loss": -2500.00,
            "profit_loss_pct": -3.23,
        },
    ]
