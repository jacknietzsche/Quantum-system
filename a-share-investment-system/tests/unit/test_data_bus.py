"""Tests for services.data_bus - DatabaseBackedDataBus."""


class TestDatabaseBackedDataBus:
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

    def test_invalidate_cache(self):
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
