"""Phase 2 Agent工具层测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.market_state import detect_market_state, get_position_cap
from tools.paper_trading import AShareBroker
from tools.technical_indicators import compute_indicators, get_latest_indicators


class TestTechnicalIndicators:
    @pytest.fixture
    def sample_df(self):
        np.random.seed(42)
        dates = pd.date_range("2026-01-01", periods=100, freq="B")
        prices = 1500 + np.cumsum(np.random.normal(0, 10, 100))
        return pd.DataFrame(
            {
                "date": dates,
                "open": prices - 5,
                "high": prices + 10,
                "low": prices - 10,
                "close": prices,
                "volume": np.random.randint(500000, 2000000, 100),
            }
        )

    def test_compute_indicators_adds_columns(self, sample_df):
        result = compute_indicators(sample_df)
        expected = [
            "ma5",
            "ma20",
            "ma60",
            "macd",
            "macd_signal",
            "rsi_14",
            "bb_upper",
            "bb_lower",
            "atr_14",
        ]
        for col in expected:
            assert col in result.columns

    def test_get_latest_indicators(self, sample_df):
        indicators = get_latest_indicators(sample_df)
        assert "close" in indicators
        assert "ma5" in indicators
        assert "rsi_14" in indicators
        assert 0 < indicators["rsi_14"] < 100


class TestMarketState:
    def test_bull_market(self):
        data = {
            "sh_change_20d": 0.10,
            "advance_count": 3000,
            "decline_count": 1000,
            "volume": 5000,
            "volume_ma20": 3000,
            "north_flow_5d": 100,
        }
        assert detect_market_state(data) == "BULL"

    def test_bear_market(self):
        data = {
            "sh_change_20d": -0.03,
            "advance_count": 1000,
            "decline_count": 3000,
            "volume": 2500,
            "volume_ma20": 3500,
            "north_flow_5d": -20,
        }
        assert detect_market_state(data) == "BEAR"

    def test_neutral_market(self):
        data = {
            "sh_change_20d": 0.01,
            "advance_count": 2000,
            "decline_count": 2000,
            "volume": 3000,
            "volume_ma20": 3000,
            "north_flow_5d": 10,
        }
        assert detect_market_state(data) == "NEUTRAL"

    def test_position_cap(self):
        assert get_position_cap("PANIC") == 0.10
        assert get_position_cap("BEAR") == 0.30
        assert get_position_cap("NEUTRAL") == 0.60
        assert get_position_cap("BULL") == 0.80


class TestPaperTrading:
    def test_buy_sell(self):
        broker = AShareBroker(initial_capital=1_000_000)
        assert broker.buy("600519", 1500.0, 100, "2026-01-01") is True
        assert "600519" in broker.positions
        assert broker.sell("600519", 1550.0, "2026-01-02") is True
        assert "600519" not in broker.positions
        assert len(broker.trades) == 2

    def test_buy_rejects_non_100(self):
        broker = AShareBroker()
        assert broker.buy("600519", 1500.0, 150, "2026-01-01") is False

    def test_buy_rejects_insufficient_funds(self):
        broker = AShareBroker(initial_capital=100)
        assert broker.buy("600519", 1500.0, 100, "2026-01-01") is False

    def test_metrics(self):
        broker = AShareBroker(initial_capital=1_000_000)
        broker.buy("600519", 1500.0, 100, "2026-01-01")
        broker.record_nav("2026-01-01", {"600519": 1500.0})
        broker.sell("600519", 1550.0, "2026-01-02")
        broker.record_nav("2026-01-02", {"600519": 1550.0})
        metrics = broker.get_metrics()
        assert "total_return" in metrics
        assert "max_drawdown" in metrics
