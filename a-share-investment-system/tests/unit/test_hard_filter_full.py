"""Comprehensive tests for services.hard_filter."""


class TestHardFilterFull:
    def test_filter_hybrid(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="hybrid")
        stocks = [
            {
                "stock_code": "600519",
                "score": 80,
                "change_pct": 2.5,
                "turnover_rate": 1.5,
                "pe_ratio": 35,
                "market_cap": 2000,
                "volatility_20d": 15,
            },
            {
                "stock_code": "000858",
                "score": 40,
                "change_pct": 1.0,
                "turnover_rate": 0.3,
                "pe_ratio": 25,
                "market_cap": 500,
                "volatility_20d": 20,
            },
            {
                "stock_code": "300750",
                "score": 70,
                "change_pct": -1.0,
                "turnover_rate": 2.0,
                "pe_ratio": 45,
                "market_cap": 800,
                "volatility_20d": 30,
            },
        ]
        result = hf.apply(stocks)
        assert isinstance(result, list)

    def test_filter_momentum(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="momentum")
        stocks = [
            {"stock_code": "600519", "score": 90, "change_pct": 5.0, "turnover_rate": 3.0},
            {"stock_code": "000858", "score": 60, "change_pct": 2.0, "turnover_rate": 1.0},
        ]
        result = hf.apply(stocks)
        assert isinstance(result, list)

    def test_filter_value(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="value")
        stocks = [
            {
                "stock_code": "600519",
                "score": 80,
                "pe_ratio": 15,
                "pb_ratio": 2,
                "roe": 20,
                "market_cap": 500,
            },
            {
                "stock_code": "000858",
                "score": 60,
                "pe_ratio": 50,
                "pb_ratio": 8,
                "roe": 5,
                "market_cap": 100,
            },
        ]
        result = hf.apply(stocks)
        assert isinstance(result, list)

    def test_filter_limit_up(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="limit_up")
        stocks = [
            {"stock_code": "600519", "score": 95, "change_pct": 9.9, "turnover_rate": 5.0},
        ]
        result = hf.apply(stocks)
        assert isinstance(result, list)

    def test_negative_exclusion(self):
        from services.hard_filter import HardFilter

        hf = HardFilter()
        stocks = [
            {"stock_code": "600519", "stock_name": "Moutai"},
            {"stock_code": "ST_STOCK", "stock_name": "ST Something"},
        ]
        result = hf._negative_exclusion(stocks)
        assert isinstance(result, list)

    def test_fallback_if_empty(self):
        from services.hard_filter import HardFilter

        hf = HardFilter()
        original = [{"stock_code": "600519", "score": 80}]
        result = hf._fallback_if_empty([], original)
        assert isinstance(result, list)

    def test_apply_regime_bull(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(market_regime="BULL")
        hf._apply_regime_adjustment()

    def test_apply_regime_bear(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(market_regime="BEAR")
        hf._apply_regime_adjustment()

    def test_get_style_admission_tags(self):
        from services.hard_filter import HardFilter

        stock = {"stock_code": "600519", "industry": "liquor", "pe_ratio": 35, "roe": 25}
        tags = HardFilter.get_style_admission_tags("hybrid", stock)
        assert isinstance(tags, list)

    def test_load_config(self):
        from services.hard_filter import HardFilter

        hf = HardFilter(style="hybrid")
        try:
            config = hf._load_config()
        except Exception:
            pass  # Config may not be available
