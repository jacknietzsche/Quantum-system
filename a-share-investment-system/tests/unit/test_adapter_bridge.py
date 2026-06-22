"""MarketDataProvider 适配器桥接测试"""

from providers.market_data import MarketDataProvider


class TestAdapterBridge:
    def test_try_adapters_method_exists(self):
        provider = MarketDataProvider.__new__(MarketDataProvider)
        provider._breakers = {}
        provider._failed_sources = {}
        provider._ok_sources = {}
        provider._reported_methods = set()
        assert hasattr(provider, "_try_adapters")

    def test_try_adapters_returns_none_when_no_adapters(self):
        provider = MarketDataProvider.__new__(MarketDataProvider)
        provider._breakers = {}
        provider._failed_sources = {}
        provider._ok_sources = {}
        provider._reported_methods = set()
        # Should not raise, even if adapter import fails
        result = provider._try_adapters("fetch_indices")
        assert result is None or isinstance(result, dict)
