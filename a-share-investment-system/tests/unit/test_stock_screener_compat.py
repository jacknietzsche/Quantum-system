"""Tests for services.screening.compat - StockScreener."""


class TestStockScreenerCompat:
    def test_init_default(self):
        from services.screening.compat import StockScreener

        ss = StockScreener()
        assert ss is not None

    def test_init_with_style(self):
        from services.screening.compat import StockScreener

        ss = StockScreener(style="momentum")
        assert ss is not None

    def test_get_metrics(self):
        from services.screening.compat import StockScreener

        ss = StockScreener()
        metrics = ss.get_metrics()
        assert isinstance(metrics, dict)

    def test_health_check(self):
        from services.screening.compat import StockScreener

        ss = StockScreener()
        result = ss.health_check()
        assert isinstance(result, bool)

    def test_classify_stock_category(self):
        from services.screening.compat import classify_stock_category

        result = classify_stock_category("600519", "Moutai")
        assert isinstance(result, str)


class TestScreeningPipeline:
    def test_init(self):
        from services.screening.pipeline import ScreeningPipeline
        from services.screening.styles import StyleConfig

        sp = ScreeningPipeline(style_config=StyleConfig())
        assert sp is not None
