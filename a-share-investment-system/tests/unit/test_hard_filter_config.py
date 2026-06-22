"""HardFilter 配置验证 + 动态阈值 单元测试"""

from services.hard_filter import (
    CONFIG_REQUIRED_FIELDS,
    REGIME_ADJUSTMENT,
    ConfigValidator,
    HardFilter,
)


class TestConfigValidator:
    def test_required_fields_defined(self):
        assert len(CONFIG_REQUIRED_FIELDS) >= 5
        assert "min_amount" in CONFIG_REQUIRED_FIELDS
        assert "min_roe" in CONFIG_REQUIRED_FIELDS

    def test_validate_returns_bool(self):
        result = ConfigValidator.validate_all()
        assert isinstance(result, bool)


class TestRegimeAdjustment:
    def test_regime_adjustments_defined(self):
        for regime in ("BULL", "BEAR", "VOLATILE"):
            assert regime in REGIME_ADJUSTMENT

    def test_bull_raises_thresholds(self):
        adj = REGIME_ADJUSTMENT["BULL"]
        for k, v in adj.items():
            assert v >= 1.0, f"{k} should increase in BULL"

    def test_bear_relaxes_or_maintains_thresholds(self):
        adj = REGIME_ADJUSTMENT["BEAR"]
        for k, v in adj.items():
            # min_* thresholds should decrease (relax); max_* may increase (expand range)
            if k.startswith("min_"):
                assert v <= 1.0, f"{k} min threshold should decrease in BEAR"
            elif k.startswith("max_"):
                assert v >= 1.0, f"{k} max threshold should increase/expand in BEAR"


class TestHardFilterInit:
    def test_default_init(self):
        hf = HardFilter("hybrid")
        assert hf.style == "hybrid"
        assert hf.market_regime == "NEUTRAL"
        assert hf.min_amount > 0

    def test_init_with_regime(self):
        hf = HardFilter("limit_up", "BULL")
        assert hf.market_regime == "BULL"

    def test_regime_overrides_loaded(self):
        hf = HardFilter("limit_up")
        assert hasattr(hf, "_regime_overrides")

    def test_all_styles_load_configs(self):
        for style in ("limit_up", "momentum", "value", "hybrid"):
            hf = HardFilter(style)
            assert hf.min_amount is not None or style != "limit_up"
            assert hf.style == style


class TestNegativeExclusion:
    def test_exclude_st_stocks(self):
        hf = HardFilter("hybrid")
        stocks = [
            {"stock_code": "600001", "stock_name": "正常股票", "price": 10, "listing_days": 500},
            {"stock_code": "600002", "stock_name": "*ST股票", "price": 5, "listing_days": 500},
            {"stock_code": "600003", "stock_name": "ST股票", "price": 3, "listing_days": 500},
            {"stock_code": "600004", "stock_name": "退市股", "price": 1, "listing_days": 500},
        ]
        passed = hf._negative_exclusion(stocks)
        assert len(passed) == 1
        assert passed[0]["stock_code"] == "600001"

    def test_exclude_zero_price(self):
        hf = HardFilter("hybrid")
        stocks = [
            {"stock_code": "600001", "stock_name": "正常", "price": 0, "listing_days": 500},
            {"stock_code": "600002", "stock_name": "正常", "price": 10, "listing_days": 500},
        ]
        passed = hf._negative_exclusion(stocks)
        assert len(passed) == 1
        assert passed[0]["stock_code"] == "600002"


class TestFallbackIfEmpty:
    def test_fallback_ensures_minimum(self):
        hf = HardFilter("hybrid")
        universe = [
            {
                "stock_code": f"{i:06d}",
                "stock_name": "股票",
                "price": 10,
                "amount": 100000000 * (100 - i),
            }
            for i in range(60)
        ]
        passed = hf._fallback_if_empty([], universe)
        assert len(passed) >= 50
