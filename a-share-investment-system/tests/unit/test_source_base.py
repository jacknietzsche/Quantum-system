"""Tests for providers/source_base.py - CircuitBreaker, RateLimiter, etc."""

import pytest


class TestCircuitBreaker:
    def test_init_defaults(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test")
        assert cb.name == "test"
        assert cb.failure_threshold == 3

    def test_init_custom(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=60)
        assert cb.failure_threshold == 5

    def test_try_acquire_closed(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test")
        assert cb.try_acquire() is True

    def test_record_failure_increments(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=5)
        cb.record_failure()
        assert cb.stats.failure_count == 1
        cb.record_failure()
        assert cb.stats.failure_count == 2

    def test_opens_after_threshold(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.try_acquire() is False

    def test_record_success(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test")
        cb.record_success()
        assert cb.stats.success_count == 1

    def test_reset(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        cb.reset()
        assert cb.try_acquire() is True

    def test_status_dict(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test")
        status = cb.status_dict()
        assert "state" in status
        assert "failures" in status

    def test_peek_available_closed(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test")
        assert cb.peek_available() is True

    def test_peek_available_open(self):
        from providers.source_base import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert cb.peek_available() is False


class TestRateLimiter:
    def test_init(self):
        from providers.source_base import RateLimiter

        rl = RateLimiter(total=5, name="test")
        assert rl._total == 5

    def test_acquire_release(self):
        from providers.source_base import RateLimiter

        rl = RateLimiter(total=5, acquire_timeout=1.0, name="test")
        acquired = rl.acquire()
        assert acquired is True
        rl.release()

    def test_acquire_timeout(self):
        from providers.source_base import RateLimiter

        rl = RateLimiter(total=1, acquire_timeout=0.1, name="test")
        rl.acquire()
        result = rl.acquire()
        assert result is False
        rl.release()


class TestCircuitBreakerStats:
    def test_default_values(self):
        from providers.source_base import CircuitBreakerStats

        stats = CircuitBreakerStats()
        assert stats.failure_count == 0
        assert stats.success_count == 0
        assert stats.total_calls == 0

    def test_state_field(self):
        from providers.source_base import CircuitBreakerStats

        stats = CircuitBreakerStats()
        assert stats.state is not None


class TestExceptions:
    def test_data_source_error(self):
        from providers.source_base import DataSourceError

        e = DataSourceError("test error")
        assert "test error" in str(e)

    def test_transient_error_is_datasource(self):
        from providers.source_base import DataSourceError, TransientError

        e = TransientError("transient")
        assert isinstance(e, DataSourceError)

    def test_permanent_error_is_datasource(self):
        from providers.source_base import DataSourceError, PermanentError

        e = PermanentError("permanent")
        assert isinstance(e, DataSourceError)

    def test_rate_limit_error_is_transient(self):
        from providers.source_base import RateLimitError, TransientError

        e = RateLimitError("rate limited")
        assert isinstance(e, TransientError)


class TestSourceAdapter:
    def test_requires_name(self):
        from providers.source_base import SourceAdapter

        with pytest.raises(ValueError):
            SourceAdapter()

    def test_subclass_with_name(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "my_source"
            priority = 1

        adapter = MySource()
        assert adapter.name == "my_source"
        assert adapter.priority == 1

    def test_fetch_indices_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_indices() is None

    def test_fetch_stock_spot_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_stock_spot() is None

    def test_fetch_kline_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_kline("600519") is None

    def test_fetch_north_flow_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_north_flow() is None

    def test_fetch_basic_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_basic("600519") is None

    def test_fetch_hot_stocks_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_hot_stocks() is None

    def test_fetch_full_spot_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_full_spot() is None

    def test_fetch_etf_spot_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert adapter.fetch_etf_spot() is None

    def test_test_connect_default(self):
        from providers.source_base import SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        result = adapter.test_connect()
        assert isinstance(result, bool)

    def test_http_property(self):
        from providers.source_base import HttpClientPool, SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        pool = adapter.http
        assert isinstance(pool, HttpClientPool)

    def test_cb_property(self):
        from providers.source_base import CircuitBreaker, SourceAdapter

        class MySource(SourceAdapter):
            name = "test"

        adapter = MySource()
        assert isinstance(adapter.cb, CircuitBreaker)


class TestHttpClientPool:
    def test_init(self):
        from providers.source_base import HttpClientPool

        pool = HttpClientPool(name="test", timeout=10.0)
        assert pool.name == "test"

    def test_pool_stats(self):
        from providers.source_base import HttpClientPool

        pool = HttpClientPool(name="test")
        stats = pool.pool_stats()
        assert isinstance(stats, dict)

    def test_get_pool_singleton(self):
        from providers.source_base import HttpClientPool

        p1 = HttpClientPool.get_pool("singleton_test_123")
        p2 = HttpClientPool.get_pool("singleton_test_123")
        assert p1 is p2

    def test_close(self):
        from providers.source_base import HttpClientPool

        pool = HttpClientPool(name="close_test_123")
        pool.close()  # should not raise
