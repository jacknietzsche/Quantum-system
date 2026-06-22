"""Tests for services.hard_filter - HardFilter."""


class TestHardFilter:
    def test_init_default(self):
        from services.hard_filter import HardFilter

        hf = HardFilter()
        assert hf.style == "hybrid"

    def test_init_custom_style(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="momentum", market_regime="BULL")
        assert hf.style == "momentum"

    def test_apply_empty(self):
        from services.hard_filter import HardFilter

        hf = HardFilter()
        result = hf.apply([])
        assert isinstance(result, list)

    def test_apply_with_stocks(self):
        from services.hard_filter import HardFilter

        hf = HardFilter()
        universe = [
            {
                "stock_code": "600519",
                "stock_name": "Moutai",
                "score": 80,
                "change_pct": 2.5,
                "turnover_rate": 1.5,
                "pe_ratio": 35,
                "market_cap": 2000,
            },
            {
                "stock_code": "000858",
                "stock_name": "Wuliangye",
                "score": 70,
                "change_pct": 1.0,
                "turnover_rate": 0.8,
                "pe_ratio": 25,
                "market_cap": 500,
            },
        ]
        result = hf.apply(universe)
        assert isinstance(result, list)

    def test_get_style_admission_tags(self):
        from services.hard_filter import HardFilter

        stock = {"stock_code": "600519", "industry": "liquor", "pe_ratio": 35}
        tags = HardFilter.get_style_admission_tags("hybrid", stock)
        assert isinstance(tags, list)

    def test_apply_regime_bull(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(market_regime="BULL")
        universe = [
            {"stock_code": "600519", "score": 80, "change_pct": 2.5, "turnover_rate": 1.5},
        ]
        result = hf.apply(universe)
        assert isinstance(result, list)

    def test_apply_regime_bear(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(market_regime="BEAR")
        universe = [
            {"stock_code": "600519", "score": 80, "change_pct": -2.5, "turnover_rate": 0.5},
        ]
        result = hf.apply(universe)
        assert isinstance(result, list)

    def test_apply_limit_up_style(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="limit_up")
        universe = [
            {"stock_code": "600519", "score": 90, "change_pct": 9.9, "turnover_rate": 5.0},
        ]
        result = hf.apply(universe)
        assert isinstance(result, list)
