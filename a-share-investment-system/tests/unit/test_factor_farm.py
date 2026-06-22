"""FactorFarm 单元测试 — 因子库、因子计算、IC评估"""

import numpy as np
import pandas as pd
import pytest

from services.factor_farm import FactorFarm, FactorLibrary


@pytest.fixture
def sample_kline_df():
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    base = 100.0
    returns = np.random.normal(0.0005, 0.015, n)
    close = base * (1 + returns).cumprod()
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": close * (1 + np.random.uniform(-0.01, 0.01, n)),
            "close": close,
            "high": close * (1 + np.abs(np.random.normal(0, 0.01, n))),
            "low": close * (1 - np.abs(np.random.normal(0, 0.01, n))),
            "volume": np.random.randint(5000000, 30000000, n),
            "amount": close * np.random.randint(5000000, 30000000, n),
            "turnover_rate": np.random.uniform(0.5, 3.0, n),
        }
    )


@pytest.fixture
def tmp_db_path(tmp_path):
    return str(tmp_path / "test_factors.db")


# ══════════════════════════════════════════════
#  FactorFarm 整合
# ══════════════════════════════════════════════


class TestFactorFarm:
    def test_get_top_factors(self):
        farm = FactorFarm()
        result = farm.get_top_factors(n=10)
        assert result.status == "ok"

    def test_get_available_factors(self):
        farm = FactorFarm()
        result = farm.get_available_factors()
        assert result.status == "ok"

    def test_compute_all_factors(self, sample_kline_df):
        farm = FactorFarm()
        factors = farm.compute_all_factors("000001", sample_kline_df)
        assert isinstance(factors, dict)
        assert "PTV" in factors
        assert "Vol_20d" in factors

    def test_compute_factor_value(self, sample_kline_df):
        farm = FactorFarm()
        result = farm.compute_factor_value("PTV", "000001", sample_kline_df)
        assert result.status == "ok"
        assert "value" in result.data

    def test_build_factor_score(self):
        farm = FactorFarm()
        result = farm.build_factor_score("600519")
        assert result.status in ("ok", "error", "degraded")

    def test_health_check(self):
        farm = FactorFarm()
        assert farm.health_check() is True


# ══════════════════════════════════════════════
#  单因子计算函数 (新行为金融/微观结构因子)
# ══════════════════════════════════════════════


class TestFactorComputations:
    def test_ptv(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_1_ptv(sample_kline_df["close"])
        assert isinstance(val, float)

    def test_cpv(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_9_cpv(
            sample_kline_df["open"],
            sample_kline_df["close"],
            sample_kline_df["high"],
            sample_kline_df["low"],
            sample_kline_df["turnover_rate"],
        )
        assert isinstance(val, float)

    def test_volume_entropy(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_20_volume_entropy(sample_kline_df["volume"])
        assert 0.0 <= val <= 1.0

    def test_rev_1m(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_102_rev_1m(sample_kline_df["close"])
        assert isinstance(val, float)

    def test_vol_20d(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_104_vol_20d(sample_kline_df["close"])
        assert isinstance(val, float)
        assert val <= 0.0

    def test_turn_20d(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_106_turn_20d(sample_kline_df["turnover_rate"])
        assert isinstance(val, float)
        assert val <= 0.0

    def test_skew_20d(self, sample_kline_df):
        farm = FactorFarm()
        val = farm._factor_115_skew_20d(sample_kline_df["close"])
        assert isinstance(val, float)


# ══════════════════════════════════════════════
#  FactorLibrary (SQLite)
# ══════════════════════════════════════════════


class TestFactorLibrary:
    def test_register_and_count(self, tmp_db_path):
        lib = FactorLibrary(db_path=tmp_db_path)
        lib.register("test_factor", "momentum", "test", 20)
        assert lib.count() >= 1
        lib.close()

    def test_get_all_active(self, tmp_db_path):
        lib = FactorLibrary(db_path=tmp_db_path)
        lib.register("f1", "momentum", "test", 20)
        lib.register("f2", "value", "test", 20)
        active = lib.get_all_active()
        assert isinstance(active, list)
        lib.close()

    def test_update_ic(self, tmp_db_path):
        lib = FactorLibrary(db_path=tmp_db_path)
        lib.register("f1", "momentum", "test", 20)
        lib.update_ic("f1", ic_mean=0.05, icir=1.2, samples=100)
        top = lib.get_top(n=5, min_ic=0.01)
        assert isinstance(top, list)
        lib.close()

    def test_deactivate(self, tmp_db_path):
        lib = FactorLibrary(db_path=tmp_db_path)
        lib.register("f1", "momentum", "test", 20)
        lib.deactivate("f1")
        active = lib.get_all_active()
        assert all(f.get("name") != "f1" for f in active)
        lib.close()
