"""MarketService ???? ? ?????"""

from services.market import MarketService


class TestMarketServiceInterface:
    def test_class_exists(self):
        assert MarketService is not None

    def test_has_get_indices(self):
        assert hasattr(MarketService, "get_indices")

    def test_has_get_north_flow(self):
        assert hasattr(MarketService, "get_north_flow")

    def test_has_get_hot_stocks(self):
        assert hasattr(MarketService, "get_hot_stocks")

    def test_has_get_sectors(self):
        assert hasattr(MarketService, "get_sectors")

    def test_has_refresh_all(self):
        assert hasattr(MarketService, "refresh_all")
