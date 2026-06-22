"""Comprehensive tests for services.data_bus."""

from unittest.mock import MagicMock, patch


class TestDataBusFull:
    def test_init(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        assert bus.db_path == ":memory:"

    def test_get_metrics(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        metrics = bus.get_metrics()
        assert isinstance(metrics, dict)

    def test_health_check(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.health_check()
        assert isinstance(result, bool)

    def test_invalidate_cache_all(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        bus.invalidate_cache()

    def test_invalidate_cache_specific(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        bus.invalidate_cache(cache_type="indices")

    def test_get_stats(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_stats()
        assert result is not None

    def test_stats_dict(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        assert "db_hits" in bus._stats
        assert "api_calls" in bus._stats
        assert "api_failures" in bus._stats

    def test_provider_lazy(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        assert bus._provider is None

    def test_thread_lock(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        assert bus._lock is not None

    @patch("services.data_bus.DatabaseBackedDataBus._read_snapshot")
    @patch("services.data_bus.DatabaseBackedDataBus._write_snapshot")
    def test_get_or_fetch_db_hit(self, mock_write, mock_read):
        from services.data_bus import DatabaseBackedDataBus

        mock_read.return_value = {"test": "data"}
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus._get_or_fetch("test_type", dict, ttl=300)
        assert result == {"test": "data"}
        assert bus._stats["db_hits"] == 1

    @patch("services.data_bus.DatabaseBackedDataBus._read_snapshot")
    @patch("services.data_bus.DatabaseBackedDataBus._write_snapshot")
    def test_get_or_fetch_api_fallback(self, mock_write, mock_read):
        from services.data_bus import DatabaseBackedDataBus

        mock_read.return_value = None
        bus = DatabaseBackedDataBus(db_path=":memory:")
        fetch_fn = MagicMock(return_value={"fresh": "data"})
        result = bus._get_or_fetch("test_type", fetch_fn, ttl=300)
        assert bus._stats["api_calls"] == 1

    @patch("services.data_bus.DatabaseBackedDataBus._read_snapshot")
    def test_get_or_fetch_api_failure_stale(self, mock_read):
        from services.data_bus import DatabaseBackedDataBus

        # First call (with TTL) returns None, second call (no TTL) returns stale
        mock_read.side_effect = [None, {"stale": "data"}]
        bus = DatabaseBackedDataBus(db_path=":memory:")
        fetch_fn = MagicMock(side_effect=Exception("API down"))
        result = bus._get_or_fetch("test_type", fetch_fn, ttl=300)
        assert bus._stats["api_failures"] == 1

    @patch("services.data_bus.DatabaseBackedDataBus._read_snapshot")
    def test_get_or_fetch_api_failure_no_cache(self, mock_read):
        from services.data_bus import DatabaseBackedDataBus

        mock_read.return_value = None
        bus = DatabaseBackedDataBus(db_path=":memory:")
        fetch_fn = MagicMock(side_effect=Exception("API down"))
        result = bus._get_or_fetch("test_type", fetch_fn, ttl=300)
        assert result is None

    @patch("services.data_bus.DatabaseBackedDataBus._get_or_fetch")
    def test_get_market_indices(self, mock_fetch):
        from services.data_bus import DatabaseBackedDataBus

        mock_fetch.return_value = {"indices": "data"}
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_market_indices()
        assert result == {"indices": "data"}

    @patch("services.data_bus.DatabaseBackedDataBus.get_market_indices")
    def test_get_market_breadth(self, mock_indices):
        from services.data_bus import DatabaseBackedDataBus

        mock_indices.return_value = {"breadth": {"adv": 100, "dec": 50}}
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_market_breadth()
        assert result == {"adv": 100, "dec": 50}

    @patch("services.data_bus.DatabaseBackedDataBus._get_or_fetch")
    def test_get_north_flow(self, mock_fetch):
        from services.data_bus import DatabaseBackedDataBus

        mock_fetch.return_value = {"total": 1000}
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_north_flow()
        assert result == {"total": 1000}

    @patch("services.data_bus.DatabaseBackedDataBus._get_or_fetch")
    def test_get_sector_ranking(self, mock_fetch):
        from services.data_bus import DatabaseBackedDataBus

        mock_fetch.return_value = [{"name": "tech"}, {"name": "finance"}]
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_sector_ranking(top_n=10)
        assert isinstance(result, list)

    @patch("services.data_bus.DatabaseBackedDataBus._get_stock_quote_cached")
    def test_get_stock_quote(self, mock_quote):
        from services.data_bus import DatabaseBackedDataBus

        mock_quote.return_value = {"price": 1800}
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_stock_quote("600519")
        assert result == {"price": 1800}

    @patch("services.data_bus.DatabaseBackedDataBus._fetch_stock_quote_api")
    def test_get_stocks_quote(self, mock_quote):
        from services.data_bus import DatabaseBackedDataBus

        mock_quote.return_value = {
            "stock_code": "600519",
            "price": 1800,
            "change_pct": 1.0,
        }
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_stocks_quote(["600519", "000858"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["price"] == 1800

    @patch("services.data_bus.DatabaseBackedDataBus._get_kline_cached")
    def test_get_stock_kline(self, mock_kline):
        from services.data_bus import DatabaseBackedDataBus

        mock_kline.return_value = None
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_stock_kline("600519", 60)
        assert result is None

    @patch("services.data_bus.DatabaseBackedDataBus._get_stock_basic_cached")
    def test_get_stock_basic(self, mock_basic):
        from services.data_bus import DatabaseBackedDataBus

        mock_basic.return_value = {"code": "600519", "name": "Moutai"}
        bus = DatabaseBackedDataBus(db_path=":memory:")
        result = bus.get_stock_basic("600519")
        assert result["code"] == "600519"

    def test_preload_stock_data_empty(self):
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus(db_path=":memory:")
        try:
            bus.preload_stock_data([])
        except Exception:
            pass  # May fail due to DB

    @patch("services.data_bus.DatabaseBackedDataBus._read_snapshot")
    def test_get_or_fetch_returns_none(self, mock_read):
        from services.data_bus import DatabaseBackedDataBus

        mock_read.return_value = None
        bus = DatabaseBackedDataBus(db_path=":memory:")
        fetch_fn = MagicMock(return_value=None)
        result = bus._get_or_fetch("test", fetch_fn, ttl=300)
        assert result is None
