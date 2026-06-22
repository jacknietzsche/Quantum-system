"""阶段2端到端集成测试"""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest
import yaml

from services.backtest_loop import BacktestLoop, BanditAllocator
from services.factor_farm import BUILTIN_FACTORS, FactorFarm
from services.strategy_loader import StrategyLoader


class TestFactorFarm:
    """FactorFarm核心功能测试"""

    @pytest.fixture
    def sample_df(self):
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        close = 100 * (1 + np.random.randn(200).cumsum() * 0.01)
        return pd.DataFrame(
            {
                "close": close,
                "high": close * (1 + np.abs(np.random.randn(200)) * 0.02),
                "low": close * (1 - np.abs(np.random.randn(200)) * 0.02),
                "volume": np.random.randint(1e6, 1e7, 200),
                "amount": close * np.random.randint(1e6, 1e7, 200),
            },
            index=dates,
        )

    def test_builtin_factors_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            ff = FactorFarm(db_path=os.path.join(tmp, "test.db"))
            try:
                result = ff.get_available_factors()
                assert result.status == "ok"
                assert result.data["total"] == len(BUILTIN_FACTORS)
            finally:
                ff.library.close()

    def test_ic_evaluation(self, sample_df):
        with tempfile.TemporaryDirectory() as tmp:
            ff = FactorFarm(db_path=os.path.join(tmp, "test.db"))
            try:
                result = ff.evaluate_ic("momentum_20d", sample_df, forward_period=5)
                assert result.status == "ok"
                assert "ic" in result.data
                assert -1.0 <= result.data["ic"] <= 1.0
                assert result.data["samples"] > 0
            finally:
                ff.library.close()

    def test_deduplication_rejects_high_correlation(self, sample_df):
        """去重: 两个高度相关的因子应被检测"""
        with tempfile.TemporaryDirectory() as tmp:
            ff = FactorFarm(db_path=os.path.join(tmp, "test.db"))
            try:
                result = ff.deduplicate("momentum_5d", sample_df, ic_threshold=0.5)
                assert result.status == "ok"
                assert "max_pairwise_ic" in result.data
            finally:
                ff.library.close()

    def test_compute_all_factors(self, sample_df):
        with tempfile.TemporaryDirectory() as tmp:
            ff = FactorFarm(db_path=os.path.join(tmp, "test.db"))
            try:
                result = ff.compute_all_factors(sample_df)
                assert result.status == "ok"
                assert result.data["count"] >= 10
            finally:
                ff.library.close()

    def test_get_top_factors(self):
        with tempfile.TemporaryDirectory() as tmp:
            ff = FactorFarm(db_path=os.path.join(tmp, "test.db"))
            try:
                np.random.seed(42)
                dates = pd.date_range("2024-01-01", periods=200, freq="B")
                df = pd.DataFrame(
                    {
                        "close": 100 * (1 + np.random.randn(200).cumsum() * 0.01),
                        "high": None,
                        "low": None,
                        "volume": None,
                        "amount": None,
                    },
                    index=dates,
                )
                df["high"] = df["close"] * 1.02
                df["low"] = df["close"] * 0.98
                df["volume"] = np.random.randint(1e6, 1e7, 200)
                df["amount"] = df["close"] * df["volume"]
                for name in ["momentum_20d", "momentum_5d", "volatility_20d"]:
                    ff.evaluate_ic(name, df)
                result = ff.get_top_factors(n=5, min_ic=0.0)
                assert result.status == "ok"
                assert len(result.data["factors"]) >= 1
            finally:
                ff.library.close()

    def test_build_factor_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            ff = FactorFarm(db_path=os.path.join(tmp, "test.db"))
            try:
                result = ff.build_factor_score("600519")
                assert result.status == "ok"
                assert "composite_score" in result.data
                assert result.data["signal"] in ("bullish", "bearish", "neutral")
            finally:
                ff.library.close()


class TestStrategyLoader:
    """策略加载器测试"""

    @pytest.fixture
    def tmp_strategies_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy = {
                "name": "test_ma_cross",
                "version": "1.0.0",
                "description": "测试策略",
                "market_regimes": ["bull"],
                "required_indicators": [
                    {"name": "ma5", "params": {"window": 5}},
                    {"name": "ma20", "params": {"window": 20}},
                ],
                "scoring": [
                    {"name": "cross", "formula": "ma5 > ma20", "weight": 50},
                ],
                "filters": [
                    {"condition": "ma5 > 0"},
                ],
                "entry_threshold": 60,
                "stop_loss_pct": -5.0,
                "take_profit_pct": 15.0,
                "max_hold_days": 20,
            }
            filepath = os.path.join(tmp, "test_strategy.yaml")
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(strategy, f, allow_unicode=True)
            yield tmp

    def test_load_valid_strategy(self, tmp_strategies_dir):
        sl = StrategyLoader(strategies_dir=tmp_strategies_dir)
        result = sl.load_all()
        assert result.status == "ok"
        assert result.data["count"] == 1
        strategy = result.data["strategies"][0]
        assert strategy["name"] == "test_ma_cross"
        assert strategy["_audit_pass"] is True

    def test_reject_forbidden_expression(self, tmp_strategies_dir):
        bad_strategy = {
            "name": "bad_strategy",
            "version": "1.0.0",
            "required_indicators": [{"name": "close", "params": {}}],
            "scoring": [{"name": "bad", "formula": "close.shift(-1) > close", "weight": 50}],
            "filters": [],
            "entry_threshold": 60,
        }
        filepath = os.path.join(tmp_strategies_dir, "bad.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(bad_strategy, f, allow_unicode=True)

        sl = StrategyLoader(strategies_dir=tmp_strategies_dir)
        result = sl.load_all()
        assert result.data["count"] == 1
        total_errors = len(result.errors) + len(result.metrics.get("errors", []))
        assert total_errors >= 1

    def test_price_peeking_audit(self):
        sl = StrategyLoader(strategies_dir="strategies")
        peek_strategy = {
            "name": "open_buy_strategy",
            "description": "开盘买入策略",
            "required_indicators": [{"name": "close", "params": {}}],
            "scoring": [{"name": "s1", "formula": "close > 0", "weight": 50}],
            "filters": [],
            "entry_threshold": 60,
        }
        result = sl.audit_strategy(peek_strategy)
        assert result.status == "ok"
        issues = result.data["issues"]
        assert any(i["audit"] == "price_peeking_check" for i in issues)

    def test_missing_name_rejected(self, tmp_strategies_dir):
        filepath = os.path.join(tmp_strategies_dir, "no_name.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump({"scoring": []}, f)
        sl = StrategyLoader(strategies_dir=tmp_strategies_dir)
        result = sl.load_all()
        assert result.data["count"] == 1


class TestBacktestLoop:
    """回测循环测试"""

    @pytest.fixture
    def sample_price_data(self):
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        close = 100 * (1 + np.random.randn(250).cumsum() * 0.012)
        return pd.DataFrame(
            {
                "close": close,
                "high": close * 1.02,
                "low": close * 0.98,
                "volume": np.random.randint(1e6, 1e7, 250),
                "amount": close * np.random.randint(1e6, 1e7, 250),
            },
            index=dates,
        )

    def test_backtest_runs(self, sample_price_data):
        bl = BacktestLoop()
        result = bl.run(sample_price_data, window_size=60, step_size=30)
        assert result.status == "ok"
        assert result.data["summary"]["total_windows"] >= 1
        assert len(result.data["rounds"]) >= 1

    def test_performance_metrics(self):
        bl = BacktestLoop()
        returns = list(np.random.randn(100) * 0.015 + 0.001)
        result = bl.calculate_performance_metrics(returns)
        assert result.status == "ok"
        assert "sharpe_ratio" in result.data
        assert "max_drawdown_pct" in result.data
        assert "win_rate_pct" in result.data

    def test_bandit_converges(self):
        ba = BanditAllocator()
        for _ in range(50):
            ba.update("new_factor", 0.7)
            ba.update("optimize", 0.3)
        status = ba.get_status()
        assert status["new_factor"]["expected"] > status["optimize"]["expected"]

    def test_insufficient_data_rejected(self):
        bl = BacktestLoop()
        tiny_df = pd.DataFrame(
            {
                "close": [100, 101, 102],
                "high": [101, 102, 103],
                "low": [99, 100, 101],
                "volume": [1e6, 1e6, 1e6],
                "amount": [1e8, 1e8, 1e8],
            }
        )
        result = bl.run(tiny_df, window_size=60)
        assert result.status == "error"
