"""MarketDataProvider 基础设施单元测试 — CircuitBreaker, RateLimiter"""

import threading
import time

from providers.market_data import _ApiRateLimiter, _CircuitBreaker

# ══════════════════════════════════════════════
#  CircuitBreaker 断路器
# ══════════════════════════════════════════════


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = _CircuitBreaker("test")
        assert cb.is_available() is True
        assert cb._state == "closed"

    def test_success_keeps_closed(self):
        cb = _CircuitBreaker("test")
        cb.record_success()
        assert cb.is_available() is True
        assert cb._state == "closed"

    def test_failures_below_threshold(self):
        cb = _CircuitBreaker("test")
        for _ in range(cb.FAIL_THRESHOLD - 1):
            cb.record_failure()
        assert cb.is_available() is True
        assert cb._state == "closed"

    def test_failures_open_circuit(self):
        cb = _CircuitBreaker("test")
        for _ in range(cb.FAIL_THRESHOLD):
            cb.record_failure()
        assert cb._state == "open"
        assert cb.is_available() is False

    def test_cooldown_allows_half_open(self):
        cb = _CircuitBreaker("test")
        for _ in range(cb.FAIL_THRESHOLD):
            cb.record_failure()
        # Simulate cooldown passed
        cb._last_fail_time = time.time() - cb.COOLDOWN_SECONDS - 1
        assert cb.is_available() is True
        assert cb._state == "half_open"

    def test_half_open_success_closes(self):
        cb = _CircuitBreaker("test")
        cb._state = "half_open"
        cb.record_success()
        assert cb._state == "closed"

    def test_half_open_failure_reopens(self):
        cb = _CircuitBreaker("test")
        cb._state = "half_open"
        cb._failures = cb.FAIL_THRESHOLD - 1
        cb.record_failure()
        assert cb._state == "open"

    def test_success_decrements_failures(self):
        cb = _CircuitBreaker("test")
        cb._failures = 2
        cb.record_success()
        assert cb._failures == 1

    def test_success_floor_at_zero(self):
        cb = _CircuitBreaker("test")
        cb._failures = 0
        cb.record_success()
        assert cb._failures == 0

    def test_status_returns_state(self):
        cb = _CircuitBreaker("test_source")
        status = cb.status
        assert "test_source" in status or "closed" in status

    def test_multiple_sources_independent(self):
        cb1 = _CircuitBreaker("source1")
        cb2 = _CircuitBreaker("source2")
        for _ in range(cb1.FAIL_THRESHOLD):
            cb1.record_failure()
        assert cb1.is_available() is False
        assert cb2.is_available() is True


# ══════════════════════════════════════════════
#  ApiRateLimiter 频率限制器
# ══════════════════════════════════════════════


class TestApiRateLimiter:
    def test_init_defaults(self):
        limiter = _ApiRateLimiter()
        assert limiter._total is not None
        assert limiter._scheduled is not None

    def test_init_custom_limits(self):
        limiter = _ApiRateLimiter(total=3, scheduled_max=2)
        assert limiter._total is not None

    def test_acquire_and_release(self):
        limiter = _ApiRateLimiter(total=5, scheduled_max=3)
        assert limiter.acquire() is True
        limiter.release()

    def test_acquire_scheduled(self):
        limiter = _ApiRateLimiter(total=5, scheduled_max=3)
        assert limiter.acquire(is_scheduled=True) is True
        limiter.release(is_scheduled=True)

    def test_stale_reclaim(self):
        limiter = _ApiRateLimiter(total=2, scheduled_max=1)
        # Simulate a stale holder
        with limiter._mu:
            limiter._holders[99999] = time.time() - limiter.STALE_TIMEOUT - 10
        reclaimed = limiter._reclaim_stale()
        assert reclaimed >= 1

    def test_thread_safety(self):
        """并发 acquire 不会死锁"""
        limiter = _ApiRateLimiter(total=10, scheduled_max=5)
        results = []

        def worker():
            ok = limiter.acquire()
            if ok:
                results.append(True)
                limiter.release()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(results) >= 1
