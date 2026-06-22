"""移植模块的单元测试 (factor_farm / quant_analyzers / market_perception)。"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

# 这些测试不需要数据库,使用纯函数
from services.factor_farm import (
    build_default_registry,
    factor_1_ptv,
    factor_3_ltr,
    factor_8_corrrv,
    factor_9_cpv,
    factor_10_alpha_new,
    factor_11_amp_momentum,
    factor_12_umr,
    factor_13_hrv_reversal,
    factor_14_amount_volatility,
    factor_17_lowrisk_momentum,
    factor_18_str,
    factor_19_t_small,
    factor_20_volume_entropy,
    factor_21_turnover_attention,
    factor_24_roe_quality,
    factor_26_de_ratio,
    factor_27_eav,
    factor_28_gm_trend,
    factor_101_cgo,
    factor_102_rev_1m,
    factor_103_rev_12m,
    factor_104_vol_20d,
    factor_105_illiq,
    factor_106_turn_20d,
    factor_107_volstd_20d,
    factor_108_lncap,
    factor_109_bp,
    factor_110_roe,
    factor_111_gpm,
    factor_112_lev,
    factor_113_dy,
    factor_114_maxret_20d,
    factor_115_skew_20d,
)
from services.market_perception import (
    DIMENSION_WEIGHTS,
    _classify_regime,
    _detect_trading_phase,
    _score_dimensions,
    perceive,
)
from services.quant_analyzers import (
    aggregate_consensus,
    analyze_all,
    buffett_analyze,
    calculate_dcf_intrinsic_value,
    calculate_owner_earnings,
    calculate_three_stage_dcf,
    graham_analyze,
    lynch_analyze,
    munger_analyze,
    pabrai_analyze,
    taleb_analyze,
)


# ── 工厂 ──
@pytest.fixture
def sample_prices() -> pd.Series:
    """60 天随机价格序列。"""
    np.random.seed(42)
    base = 100.0
    returns = np.random.normal(0.001, 0.02, 60)
    prices = [base]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    return pd.Series(prices[1:])


@pytest.fixture
def sample_kline(sample_prices: pd.Series) -> pd.DataFrame:
    """OHLCV K线。"""
    n = len(sample_prices)
    highs = sample_prices * (1 + np.abs(np.random.normal(0, 0.01, n)))
    lows = sample_prices * (1 - np.abs(np.random.normal(0, 0.01, n)))
    opens = sample_prices * (1 + np.random.normal(0, 0.005, n))
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": sample_prices.values,
        "volume": volume,
        "amount": volume * sample_prices.values,
        "turnover_rate": np.random.uniform(0.5, 5.0, n),
    })


@pytest.fixture
def sample_info() -> dict:
    return {
        "roe": 18.0,
        "gross_margin": 35.0,
        "net_margin": 12.0,
        "pe_ratio": 15.0,
        "pb_ratio": 2.0,
        "debt_to_equity": 40.0,
        "current_ratio": 1.8,
        "eps": 2.5,
        "bvps": 8.0,
        "price": 30.0,
        "latest_price": 30.0,
        "shares_outstanding": 1000.0,
        "earnings_growth_3y": 12.0,
        "revenue_growth_3y": 8.0,
        "total_market_cap": 200.0,
        "dividend_yield": 2.0,
    }


# ── factor_farm 测试 ──
class TestFactorAlgorithms:
    def test_factor_1_ptv_returns_finite(self, sample_prices):
        v = factor_1_ptv(sample_prices)
        assert np.isfinite(v)

    def test_factor_1_ptv_short_series(self):
        v = factor_1_ptv(pd.Series([1.0, 1.01, 1.02]))
        assert v == 0.0

    def test_factor_3_ltr(self, sample_prices, sample_kline):
        v = factor_3_ltr(sample_prices, sample_kline["turnover_rate"])
        assert np.isfinite(v)

    def test_factor_8_corrrv(self, sample_prices, sample_kline):
        returns = sample_prices.pct_change()
        v = factor_8_corrrv(returns, sample_kline["volume"])
        assert -1.0 <= v <= 1.0

    def test_factor_9_cpv(self, sample_kline):
        v = factor_9_cpv(
            sample_kline["open"],
            sample_kline["close"],
            sample_kline["high"],
            sample_kline["low"],
            sample_kline["turnover_rate"],
        )
        assert np.isfinite(v)

    def test_factor_10_alpha_new(self, sample_prices, sample_kline):
        v = factor_10_alpha_new(sample_prices, sample_kline["volume"])
        assert -1.0 <= v <= 1.0

    def test_factor_11_amp_momentum(self, sample_prices, sample_kline):
        v = factor_11_amp_momentum(sample_prices, sample_kline["high"], sample_kline["low"])
        assert np.isfinite(v)

    def test_factor_12_umr(self, sample_prices, sample_kline):
        v = factor_12_umr(sample_prices, sample_kline["turnover_rate"])
        assert np.isfinite(v)

    def test_factor_13_hrv_reversal(self, sample_prices, sample_kline):
        v = factor_13_hrv_reversal(sample_prices, sample_kline["high"], sample_kline["low"])
        assert np.isfinite(v)

    def test_factor_14_amount_volatility(self, sample_prices, sample_kline):
        v = factor_14_amount_volatility(sample_prices, sample_kline["amount"])
        assert v >= 0.0

    def test_factor_17_lowrisk_momentum(self, sample_prices, sample_kline):
        v = factor_17_lowrisk_momentum(sample_prices, sample_kline["high"], sample_kline["low"])
        assert np.isfinite(v)

    def test_factor_18_str(self, sample_kline):
        v = factor_18_str(sample_kline["turnover_rate"])
        assert v >= 0.0

    def test_factor_19_t_small(self, sample_kline):
        v = factor_19_t_small(sample_kline["turnover_rate"])
        assert 0.0 <= v <= 1.0

    def test_factor_20_volume_entropy(self, sample_kline):
        v = factor_20_volume_entropy(sample_kline["volume"])
        assert 0.0 <= v <= 1.0

    def test_factor_21_turnover_attention(self, sample_prices, sample_kline):
        v = factor_21_turnover_attention(sample_prices, sample_kline["turnover_rate"])
        assert v >= 0.0

    def test_factor_101_cgo(self, sample_prices, sample_kline):
        v = factor_101_cgo(sample_prices, sample_kline["turnover_rate"])
        assert np.isfinite(v)

    def test_factor_102_rev_1m(self, sample_prices):
        v = factor_102_rev_1m(sample_prices)
        assert np.isfinite(v)

    def test_factor_103_rev_12m(self):
        long_prices = pd.Series(np.linspace(10, 12, 300))
        v = factor_103_rev_12m(long_prices)
        assert np.isfinite(v)

    def test_factor_103_rev_12m_short(self):
        v = factor_103_rev_12m(pd.Series([1, 2, 3]))
        assert v == 0.0

    def test_factor_104_vol_20d(self, sample_prices):
        v = factor_104_vol_20d(sample_prices)
        assert v <= 0.0

    def test_factor_105_illiq(self, sample_prices, sample_kline):
        v = factor_105_illiq(sample_prices, sample_kline["amount"])
        assert v >= 0.0

    def test_factor_106_turn_20d(self, sample_kline):
        v = factor_106_turn_20d(sample_kline["turnover_rate"])
        assert v <= 0.0

    def test_factor_107_volstd_20d(self, sample_kline):
        v = factor_107_volstd_20d(sample_kline["volume"])
        assert v <= 0.0

    def test_factor_108_lncap(self):
        assert factor_108_lncap(100.0) < 0
        assert factor_108_lncap(None) == 0.0
        assert factor_108_lncap(0) == 0.0

    def test_factor_109_bp(self):
        assert factor_109_bp(10.0, 5.0) == 0.5
        assert factor_109_bp(None, 5.0) == 0.0
        assert factor_109_bp(10.0, None) == 0.0

    def test_factor_110_roe(self):
        assert factor_110_roe(15.5) == 15.5
        assert factor_110_roe(None) == 0.0

    def test_factor_111_gpm(self):
        assert factor_111_gpm(35.0) == 35.0
        assert factor_111_gpm(None) == 0.0

    def test_factor_112_lev(self):
        assert factor_112_lev(40.0) == -40.0
        assert factor_112_lev(None) == 0.0

    def test_factor_113_dy(self):
        assert factor_113_dy(2.5) == 2.5
        assert factor_113_dy(None) == 0.0

    def test_factor_114_maxret_20d(self, sample_prices):
        v = factor_114_maxret_20d(sample_prices)
        assert v <= 0.0

    def test_factor_115_skew_20d(self, sample_prices):
        v = factor_115_skew_20d(sample_prices)
        assert np.isfinite(v)

    def test_factor_24_roe_quality(self, sample_info):
        v = factor_24_roe_quality(sample_info)
        assert v > 0

    def test_factor_26_de_ratio(self, sample_info):
        v = factor_26_de_ratio(sample_info)
        assert v == 40.0

    def test_factor_27_eav(self, sample_info):
        v = factor_27_eav(sample_info)
        assert v == 4.0  # 12 - 8

    def test_factor_28_gm_trend(self, sample_info):
        v = factor_28_gm_trend(sample_info)
        assert v == 35.0

    def test_default_registry_has_33_factors(self):
        reg = build_default_registry()
        assert len(reg) == 33
        assert "PTV" in reg
        assert "CGO" in reg
        assert "ROE_Quality" in reg


# ── quant_analyzers 测试 ──
class TestQuantAnalyzers:
    def test_buffett_high_roe(self, sample_info):
        sample_info["roe"] = 25.0
        sample_info["gross_margin"] = 60.0
        sample_info["debt_to_equity"] = 20.0
        result = buffett_analyze("600519", sample_info)
        assert result["score"] > 60
        assert result["signal"] == "bullish"
        assert result["details"]["moat_score"] >= 30

    def test_buffett_low_roe(self, sample_info):
        sample_info["roe"] = 2.0
        sample_info["gross_margin"] = 5.0
        result = buffett_analyze("000001", sample_info)
        assert result["score"] < 30
        assert result["signal"] == "bearish"

    def test_graham_with_ncav(self, sample_info):
        sample_info["current_assets"] = 10000
        sample_info["total_liabilities"] = 5000
        sample_info["shares_outstanding"] = 1000
        result = graham_analyze("600519", sample_info)
        assert result["details"]["has_ncav_data"] is True
        assert result["details"]["ncav_per_share"] == 5.0

    def test_graham_without_ncav_neutral_floor(self, sample_info):
        result = graham_analyze("000001", sample_info)
        assert result["details"]["has_ncav_data"] is False
        # NCAV 缺失时保底分 40
        assert result["score"] >= 40

    def test_lynch_low_peg(self, sample_info):
        sample_info["pe_ratio"] = 8
        sample_info["earnings_growth_3y"] = 20.0
        result = lynch_analyze("600519", sample_info)
        assert result["score"] >= 50
        assert result["details"]["peg"] == 0.4

    def test_taleb_low_debt(self, sample_info):
        sample_info["debt_to_equity"] = 10
        sample_info["cash_to_assets"] = 25
        result = taleb_analyze("600519", sample_info)
        assert result["score"] >= 60

    def test_munger_high_roe_low_volatility(self, sample_info):
        sample_info["roe"] = 20.0
        sample_info["roe_stability_5y"] = 1.5
        sample_info["insider_holding_pct"] = 6.0
        result = munger_analyze("600519", sample_info)
        assert result["score"] >= 50

    def test_pabrai_low_pb_high_roe(self, sample_info):
        sample_info["price"] = 5.0
        sample_info["bvps"] = 8.0
        sample_info["roe"] = 18.0
        result = pabrai_analyze("600519", sample_info)
        assert result["score"] >= 55

    def test_dcf_basic(self):
        iv = calculate_dcf_intrinsic_value(
            free_cash_flow=100.0,
            growth_rate=0.05,
            discount_rate=0.10,
            terminal_growth_rate=0.02,
            num_years=5,
        )
        assert iv > 0

    def test_dcf_negative_fcf_returns_zero(self):
        assert calculate_dcf_intrinsic_value(-10) == 0
        assert calculate_dcf_intrinsic_value(0) == 0

    def test_owner_earnings(self):
        oe = calculate_owner_earnings(
            net_income=100, depreciation=20, capex=30, working_capital_change=5
        )
        # 100 + 20 - max(30*0.85, 20) - 5 = 120 - 25.5 - 5 = 89.5
        assert oe == pytest.approx(89.5)

    def test_three_stage_dcf(self):
        result = calculate_three_stage_dcf(
            net_income=1000,
            depreciation=200,
            capex=300,
            working_capital_change=50,
            shares_outstanding=100,
            earnings_growth_3y=0.10,
        )
        assert result["intrinsic_value"] is not None
        assert result["intrinsic_value"] > 0
        assert "raw_iv" in result

    def test_three_stage_dcf_no_shares(self):
        result = calculate_three_stage_dcf(
            net_income=1000,
            depreciation=200,
            capex=300,
            working_capital_change=50,
            shares_outstanding=0,
        )
        assert result["intrinsic_value"] is None

    def test_analyze_all_runs_6_analysts(self, sample_info):
        results = analyze_all("600519", sample_info)
        assert len(results) == 6
        analysts = {r["analyst"] for r in results}
        assert analysts == {"buffett", "graham", "lynch", "taleb", "munger", "pabrai"}

    def test_analyze_all_resilient(self, sample_info):
        # Should not raise even with bad input
        results = analyze_all("000001", {"roe": None, "pe_ratio": "bad"})
        assert len(results) == 6

    def test_aggregate_consensus_bullish(self, sample_info):
        sample_info["roe"] = 25.0
        results = analyze_all("600519", sample_info)
        consensus = aggregate_consensus(results)
        assert consensus["num_analysts"] == 6
        assert "signals" in consensus

    def test_aggregate_consensus_empty(self):
        consensus = aggregate_consensus([])
        assert consensus["consensus"] == "neutral"
        assert consensus["average_score"] == 50


# ── market_perception 测试 ──
class TestMarketPerception:
    def test_dimensions_score_range(self):
        breadth = {"up": 2000, "down": 1000, "total": 3000, "limit_up": 30, "limit_down": 5}
        scores = _score_dimensions(breadth, {})
        for v in scores.values():
            assert -2.0 <= v <= 2.0

    def test_classify_bull(self):
        breadth = {"up": 2500, "down": 500, "total": 3000, "limit_up": 50, "limit_down": 5}
        regime = _classify_regime(1.5, breadth)
        assert regime == "BULL"

    def test_classify_bear(self):
        breadth = {"up": 500, "down": 2500, "total": 3000, "limit_up": 5, "limit_down": 30}
        regime = _classify_regime(-1.5, breadth)
        assert regime == "BEAR"

    def test_classify_panic(self):
        breadth = {"up": 100, "down": 2800, "total": 3000, "limit_up": 0, "limit_down": 80}
        regime = _classify_regime(-1.5, breadth)
        assert regime == "PANIC"

    def test_classify_overheat(self):
        breadth = {"up": 2900, "down": 100, "total": 3000, "limit_up": 200, "limit_down": 0}
        regime = _classify_regime(1.5, breadth)
        assert regime == "OVERHEAT"

    def test_classify_neutral(self):
        breadth = {"up": 1500, "down": 1500, "total": 3000, "limit_up": 10, "limit_down": 10}
        regime = _classify_regime(0.0, breadth)
        assert regime == "NEUTRAL"

    def test_trading_phase_weekend(self):
        # 2026-06-20 是周六
        saturday = datetime(2026, 6, 20, 10, 0)
        assert _detect_trading_phase(saturday) == "holiday"

    def test_trading_phase_morning(self):
        morning = datetime(2026, 6, 22, 10, 30)  # 周一 10:30
        assert _detect_trading_phase(morning) == "intraday_morning"

    def test_trading_phase_afternoon(self):
        afternoon = datetime(2026, 6, 22, 14, 0)  # 周一 14:00
        assert _detect_trading_phase(afternoon) == "intraday_afternoon"

    def test_trading_phase_lunch(self):
        lunch = datetime(2026, 6, 22, 12, 0)  # 周一 12:00
        assert _detect_trading_phase(lunch) == "lunch_break"

    def test_perceive_returns_expected_keys(self):
        market = {"breadth": {"up": 2000, "down": 1000, "total": 3000, "limit_up": 30, "limit_down": 5}, "indices": {}}
        result = perceive(market)
        assert "regime" in result
        assert "total_score" in result
        assert "dimension_scores" in result
        assert "adaptive_params" in result
        assert "trading_phase" in result

    def test_perceive_handles_empty_input(self):
        result = perceive({})
        assert result["regime"] == "NEUTRAL"
        assert "error" not in result or result.get("error") is not None

    def test_adaptive_params_bull(self):
        from services.market_perception import _adaptive_params

        params = _adaptive_params("BULL")
        assert params["target_position_pct"] == 0.95
        assert params["max_holdings"] == 10

    def test_adaptive_params_unknown_regime(self):
        from services.market_perception import _adaptive_params

        params = _adaptive_params("UNKNOWN")
        # 默认 NEUTRAL
        assert params["target_position_pct"] == 0.50

    def test_weights_sum_to_one(self):
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


# ── FactorLibrary SQLite 测试 ──
class TestFactorLibrary:
    def test_init_creates_db(self, tmp_path):
        from services.factor_farm import FactorLibrary

        db_path = str(tmp_path / "test_factors.db")
        lib = FactorLibrary(db_path=db_path)
        try:
            assert os.path.exists(db_path)
        finally:
            lib.close()

    def test_register_and_query(self, tmp_path):
        from services.factor_farm import FactorLibrary

        db_path = str(tmp_path / "test_factors.db")
        lib = FactorLibrary(db_path=db_path)
        try:
            assert lib.register("CUSTOM1", "test", "custom factor") is True
            rows = lib.get_all_active()
            assert any(r["name"] == "CUSTOM1" for r in rows)
        finally:
            lib.close()

    def test_register_idempotent(self, tmp_path):
        from services.factor_farm import FactorLibrary

        db_path = str(tmp_path / "test_factors.db")
        lib = FactorLibrary(db_path=db_path)
        try:
            lib.register("DUP", "test", "desc")
            lib.register("DUP", "test", "desc2")
            # 不应抛错
        finally:
            lib.close()

    def test_update_ic(self, tmp_path):
        from services.factor_farm import FactorLibrary

        db_path = str(tmp_path / "test_factors.db")
        lib = FactorLibrary(db_path=db_path)
        try:
            lib.register("IC1", "test")
            lib.update_ic("IC1", 0.05, 1.2, 100)
            rows = lib.get_all_active()
            ic1 = next(r for r in rows if r["name"] == "IC1")
            assert ic1["ic_mean"] == 0.05
            assert ic1["icir"] == 1.2
        finally:
            lib.close()

    def test_get_top_filters_by_ic(self, tmp_path):
        from services.factor_farm import FactorLibrary

        db_path = str(tmp_path / "test_factors.db")
        lib = FactorLibrary(db_path=db_path)
        try:
            lib.register("HIGH", "test")
            lib.register("LOW", "test")
            lib.update_ic("HIGH", 0.05, 1.0, 50)
            lib.update_ic("LOW", 0.005, 0.1, 50)
            top = lib.get_top(n=5, min_ic=0.02)
            names = [r["name"] for r in top]
            assert "HIGH" in names
            assert "LOW" not in names
        finally:
            lib.close()

    def test_deactivate(self, tmp_path):
        from services.factor_farm import FactorLibrary

        db_path = str(tmp_path / "test_factors.db")
        lib = FactorLibrary(db_path=db_path)
        try:
            lib.register("DEACT", "test")
            lib.deactivate("DEACT")
            rows = lib.get_all_active()
            assert all(r["name"] != "DEACT" for r in rows)
        finally:
            lib.close()


# ── FactorFarm 集成测试 ──
class TestFactorFarmIntegration:
    def test_compute_all_factors(self, sample_kline, sample_info):
        # 临时目录,避免污染
        import tempfile

        from services.factor_farm import FactorFarm
        with tempfile.TemporaryDirectory() as tmp:
            farm = FactorFarm(db_path=os.path.join(tmp, "factors.db"))
            factors = farm.compute_all_factors("600519", sample_kline, sample_info)
            assert len(factors) > 20
            # 验证一些关键因子存在
            assert "PTV" in factors
            assert "Buffett" not in factors  # Buffett 是分析师不是因子
            farm.library.close() if farm.library else None

    def test_get_all_factor_names(self):
        import tempfile

        from services.factor_farm import FactorFarm
        with tempfile.TemporaryDirectory() as tmp:
            farm = FactorFarm(db_path=os.path.join(tmp, "factors.db"))
            names = farm.get_all_factor_names()
            assert len(names) == 33
            if farm.library is not None:
                farm.library.close()

    def test_get_top_factors(self, tmp_path):
        from services.factor_farm import FactorFarm

        farm = FactorFarm(db_path=str(tmp_path / "factors.db"))
        result = farm.get_top_factors(n=10, min_ic=0.0)
        # 没填 IC, 应该返回所有注册的
        assert "factors" in result
        if farm.library is not None:
            farm.library.close()
