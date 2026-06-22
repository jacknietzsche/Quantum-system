"""providers层单元测试。"""

from __future__ import annotations

from providers.base import CircuitBreaker, CircuitState
from providers.health import DataProviderHealth
from providers.normalizer import StockCodeNormalizer


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        import time

        time.sleep(0.02)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN


class TestStockCodeNormalizer:
    def test_to_db_from_baostock(self):
        assert StockCodeNormalizer.to_db("sh.600519") == "600519"
        assert StockCodeNormalizer.to_db("sz.000001") == "000001"

    def test_to_db_from_yfinance(self):
        assert StockCodeNormalizer.to_db("600519.SS") == "600519"
        assert StockCodeNormalizer.to_db("000001.SZ") == "000001"

    def test_to_db_pure_number(self):
        assert StockCodeNormalizer.to_db("600519") == "600519"

    def test_to_baostock(self):
        assert StockCodeNormalizer.to_baostock("600519") == "sh.600519"
        assert StockCodeNormalizer.to_baostock("000001") == "sz.000001"

    def test_to_yfinance(self):
        assert StockCodeNormalizer.to_yfinance("600519") == "600519.SS"
        assert StockCodeNormalizer.to_yfinance("000001") == "000001.SZ"

    def test_get_exchange(self):
        assert StockCodeNormalizer.get_exchange("600519") == "SH"
        assert StockCodeNormalizer.get_exchange("000001") == "SZ"
        assert StockCodeNormalizer.get_exchange("430001") == "BJ"


class TestDataProviderHealth:
    def test_check_healthy(self):
        health = DataProviderHealth()
        result = health.check("test", lambda: None)
        assert result["status"] == "healthy"
        assert "latency_ms" in result

    def test_check_unhealthy(self):
        health = DataProviderHealth()
        result = health.check("test", lambda: 1 / 0)
        assert result["status"] == "unhealthy"
        assert result["error"] is not None

    def test_get_healthy_providers(self):
        health = DataProviderHealth()
        health.check("good", lambda: None)
        health.check("bad", lambda: 1 / 0)
        assert "good" in health.get_healthy_providers()
        assert "bad" not in health.get_healthy_providers()
