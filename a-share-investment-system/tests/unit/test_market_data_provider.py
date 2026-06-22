"""Tests for providers.market_data - MarketDataProvider."""


class TestMarketDataProvider:
    def test_init(self):
        from providers.market_data import MarketDataProvider

        mdp = MarketDataProvider()
        assert mdp is not None

    def test_get_source_status(self):
        from providers.market_data import MarketDataProvider

        mdp = MarketDataProvider()
        status = mdp.get_source_status()
        assert isinstance(status, dict)

    def test_reset_sources(self):
        from providers.market_data import MarketDataProvider

        mdp = MarketDataProvider()
        mdp.reset_sources()  # should not raise

    def test_reset_source_health(self):
        from providers.market_data import MarketDataProvider

        mdp = MarketDataProvider()
        mdp.reset_source_health()  # should not raise
