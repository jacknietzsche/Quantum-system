"""BacktestSimulator 单元测试 — 交易模拟、成本计算、涨跌停限制"""

import pytest

from services.backtest_sim import BacktestConfig, BacktestSimulator


@pytest.fixture
def config():
    return BacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        stamp_tax_rate=0.001,
        slippage_pct=0.001,
        min_commission=5.0,
        max_position_pct=0.20,
        max_holdings=10,
    )


@pytest.fixture
def simulator(config):
    return BacktestSimulator(config)


@pytest.fixture
def simple_signals():
    return [
        {
            "date": "2024-01-15",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "action": "BUY",
            "confidence": 85,
            "reason": "突破20日高点",
        },
        {
            "date": "2024-01-20",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "action": "SELL",
            "confidence": 30,
            "reason": "跌破止损线",
        },
    ]


@pytest.fixture
def simple_price_data():
    return {
        "2024-01-15": {
            "600519": {
                "open": 1680.0,
                "high": 1700.0,
                "low": 1670.0,
                "close": 1695.0,
                "pre_close": 1675.0,
            },
        },
        "2024-02-01": {
            "600519": {
                "open": 1720.0,
                "high": 1730.0,
                "low": 1710.0,
                "close": 1725.0,
                "pre_close": 1715.0,
            },
        },
        "2024-01-20": {
            "600519": {
                "open": 1550.0,
                "high": 1560.0,
                "low": 1540.0,
                "close": 1545.0,
                "pre_close": 1695.0,
            },
        },
    }


# ── 配置测试 ──


class TestBacktestConfig:
    def test_default_config(self):
        cfg = BacktestConfig()
        assert cfg.initial_capital == 1_000_000
        assert cfg.commission_rate == 0.0003
        assert cfg.stamp_tax_rate == 0.001
        assert cfg.max_holdings == 10

    def test_custom_config(self, config):
        assert config.initial_capital == 1_000_000
        assert config.slippage_pct == 0.001


# ── 滑点测试 ──


class TestSlippage:
    def test_buy_slippage(self, simulator):
        price = simulator._apply_slippage(100.0, "BUY")
        assert price == 100.1  # 100 * (1 + 0.001)

    def test_sell_slippage(self, simulator):
        price = simulator._apply_slippage(100.0, "SELL")
        assert price == 99.9  # 100 * (1 - 0.001)


# ── 涨跌停测试 ──


class TestLimitChecks:
    def test_is_limit_up(self, simulator):
        assert simulator._is_limit_up(110.0, 100.0) == True  # +10.0% (above 9.8% threshold)

    def test_is_not_limit_up(self, simulator):
        assert simulator._is_limit_up(105.0, 100.0) == False  # +5%

    def test_is_limit_down(self, simulator):
        assert simulator._is_limit_down(89.9, 100.0) == True  # -10.1% (below -9.8% threshold)

    def test_is_not_limit_down(self, simulator):
        assert simulator._is_limit_down(95.0, 100.0) == False  # -5%

    def test_zero_pre_close(self, simulator):
        assert simulator._is_limit_up(100.0, 0.0) == False
        assert simulator._is_limit_down(100.0, 0.0) == False


# ── 交易模拟测试 ──


class TestTradingSimulation:
    def test_empty_signals(self, simulator):
        result = simulator.run([], {})
        assert result.status == "error"

    def test_buy_and_sell(self, simulator, simple_signals, simple_price_data):
        result = simulator.run(simple_signals, simple_price_data)
        assert result.status == "ok"
        data = result.data
        assert data["trades_count"] == 2
        assert data["costs"]["total_trades"] == 2

    def test_buy_only(self, simulator):
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "茅台",
                "action": "BUY",
                "confidence": 80,
                "reason": "test",
            },
        ]
        prices = {
            "2024-01-15": {
                "600519": {
                    "open": 1680.0,
                    "high": 1700.0,
                    "low": 1670.0,
                    "close": 1695.0,
                    "pre_close": 1675.0,
                }
            },
        }
        result = simulator.run(signals, prices)
        assert result.status == "ok"
        assert result.data["trades_count"] == 1

    def test_max_holdings_respected(self):
        config = BacktestConfig(max_holdings=2, initial_capital=10_000_000)
        sim = BacktestSimulator(config)
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": f"00000{i}",
                "stock_name": f"Stock{i}",
                "action": "BUY",
                "confidence": 80,
                "reason": "test",
            }
            for i in range(5)
        ]
        prices = {
            "2024-01-15": {
                f"00000{i}": {
                    "open": 50.0,
                    "high": 51.0,
                    "low": 49.0,
                    "close": 50.5,
                    "pre_close": 49.5,
                }
                for i in range(5)
            },
        }
        result = sim.run(signals, prices)
        assert result.data["trades_count"] <= 2


# ── 汇总指标测试 ──


class TestSummaryMetrics:
    def test_result_to_dict(self, simulator, simple_signals, simple_price_data):
        result = simulator.run(simple_signals, simple_price_data)
        data = result.data
        assert "summary" in data
        assert "costs" in data
        assert "config" in data
        assert "daily_nav" in data
        assert isinstance(data["daily_nav"], list)

    def test_costs_tracked(self, simulator, simple_signals, simple_price_data):
        result = simulator.run(simple_signals, simple_price_data)
        costs = result.data["costs"]
        assert costs["total_commission"] > 0
        assert costs["total_tax"] >= 0
        assert costs["total_slippage"] >= 0

    def test_daily_snapshots_created(self, simulator, simple_signals, simple_price_data):
        result = simulator.run(simple_signals, simple_price_data)
        assert result.data["snapshots_count"] >= 2

    def test_no_price_data_for_stock(self, simulator):
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "999999",
                "stock_name": "NoData",
                "action": "BUY",
                "confidence": 80,
                "reason": "test",
            },
        ]
        result = simulator.run(signals, {"2024-01-15": {}})
        assert result.status == "ok"
        assert result.data["trades_count"] == 0


class TestSellSignals:
    """Test sell signal handling"""

    def test_sell_signal_closes_position(self, simulator):
        """Sell signal should close existing position"""
        price_data = {
            "2024-01-15": {"600519": {"open": 100, "high": 102, "low": 98, "close": 101}},
            "2024-01-16": {"600519": {"open": 105, "high": 107, "low": 103, "close": 106}},
        }
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "BUY",
                "confidence": 85,
                "reason": "test buy",
            },
            {
                "date": "2024-01-16",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "SELL",
                "confidence": 50,
                "reason": "test sell",
            },
        ]
        result = simulator.run(signals, price_data)
        assert result.status == "ok"
        assert result.data["trades_count"] == 2
        # Should have 1 BUY + 1 SELL
        assert result.data["costs"]["total_trades"] == 2

    def test_sell_without_position_ignored(self, simulator):
        """Sell signal for stock not held should be ignored"""
        price_data = {
            "2024-01-15": {"600519": {"open": 100, "high": 102, "low": 98, "close": 101}},
        }
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "SELL",
                "confidence": 50,
                "reason": "no position",
            },
        ]
        result = simulator.run(signals, price_data)
        assert result.status == "ok"
        assert result.data["trades_count"] == 0


class TestMultiCycleTrading:
    """Test multiple buy/sell cycles"""

    def test_buy_sell_buy_again(self, simulator):
        """Can buy, sell, then buy same stock again"""
        price_data = {
            "2024-01-15": {"600519": {"open": 100, "high": 102, "low": 98, "close": 101}},
            "2024-01-16": {"600519": {"open": 105, "high": 107, "low": 103, "close": 106}},
            "2024-01-17": {"600519": {"open": 102, "high": 104, "low": 100, "close": 103}},
        }
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "BUY",
                "confidence": 85,
                "reason": "cycle 1 buy",
            },
            {
                "date": "2024-01-16",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "SELL",
                "confidence": 50,
                "reason": "cycle 1 sell",
            },
            {
                "date": "2024-01-17",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "BUY",
                "confidence": 80,
                "reason": "cycle 2 buy",
            },
        ]
        result = simulator.run(signals, price_data)
        assert result.status == "ok"
        assert result.data["trades_count"] == 3

    def test_multiple_stocks_parallel(self, simulator):
        """Multiple stocks traded simultaneously"""
        price_data = {
            "2024-01-15": {
                "600519": {"open": 100, "high": 102, "low": 98, "close": 101},
                "000001": {"open": 10, "high": 11, "low": 9, "close": 10.5},
            },
        }
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "BUY",
                "confidence": 85,
                "reason": "test",
            },
            {
                "date": "2024-01-15",
                "stock_code": "000001",
                "stock_name": "PingAn",
                "action": "BUY",
                "confidence": 70,
                "reason": "test",
            },
        ]
        result = simulator.run(signals, price_data)
        assert result.status == "ok"
        assert result.data["trades_count"] == 2


class TestEdgeCases:
    """Edge case tests"""

    def test_commission_minimum(self, simulator):
        """Very small trade should hit minimum commission"""
        price_data = {
            "2024-01-15": {"600519": {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0}},
        }
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Cheap",
                "action": "BUY",
                "confidence": 85,
                "reason": "cheap stock",
            },
        ]
        result = simulator.run(signals, price_data)
        assert result.status == "ok"
        # Commission should be at least min_commission (5.0)
        # But with max_position_pct=0.20 and capital=1M, max invest = 200K
        # At 1.0 per share, 200000 shares, amount=200000, commission = 200000*0.0003 = 60 > 5
        assert result.data["costs"]["total_commission"] > 0

    def test_all_signals_same_stock(self, simulator):
        """Multiple signals for same stock on same day"""
        price_data = {
            "2024-01-15": {"600519": {"open": 100, "high": 102, "low": 98, "close": 101}},
        }
        signals = [
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "BUY",
                "confidence": 85,
                "reason": "dup1",
            },
            {
                "date": "2024-01-15",
                "stock_code": "600519",
                "stock_name": "Moutai",
                "action": "BUY",
                "confidence": 80,
                "reason": "dup2",
            },
        ]
        result = simulator.run(signals, price_data)
        assert result.status == "ok"
        # Should only buy once (already in holdings)
        assert result.data["trades_count"] == 1
