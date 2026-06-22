"""运行时监控模块单元测试"""

from services.monitor import HealthMetrics, RuntimeMonitor, get_monitor


class TestHealthMetrics:
    def test_initial_state_is_healthy(self):
        m = HealthMetrics("test")
        assert m.is_healthy is True
        assert m.success_rate == 1.0

    def test_record_success(self):
        m = HealthMetrics("test")
        m.record(True, latency_ms=100)
        assert m.success_rate == 1.0
        assert m.is_healthy is True
        assert m.consecutive_failures == 0

    def test_record_failure(self):
        m = HealthMetrics("test")
        m.record(False)
        assert m.success_rate == 0.0
        assert m.is_healthy is False
        assert m.consecutive_failures == 1

    def test_mixed_results(self):
        m = HealthMetrics("test")
        for _ in range(8):
            m.record(True)
        for _ in range(2):
            m.record(False)
        assert m.success_rate == 0.8
        assert m.is_healthy is True

    def test_consecutive_failures_trigger_unhealthy(self):
        m = HealthMetrics("test")
        for _ in range(5):
            m.record(False)
        assert m.is_healthy is False
        assert m.consecutive_failures == 5

    def test_avg_latency(self):
        m = HealthMetrics("test")
        m.record(True, latency_ms=100)
        m.record(True, latency_ms=200)
        assert m.avg_latency_ms == 150.0

    def test_to_dict(self):
        m = HealthMetrics("test")
        m.record(True, latency_ms=100)
        d = m.to_dict()
        assert d["name"] == "test"
        assert d["total_requests"] == 1
        assert "success_rate" in d
        assert "is_healthy" in d


class TestRuntimeMonitor:
    def test_singleton(self):
        m1 = RuntimeMonitor()
        m2 = RuntimeMonitor()
        assert m1 is m2

    def test_record_data_source(self):
        m = get_monitor()
        m.record_data_source("akshare", True, latency_ms=500)
        metric = m.get_metric("data_source.akshare")
        assert metric.success_rate == 1.0

    def test_record_llm_call(self):
        m = get_monitor()
        m.record_llm_call("deepseek", "deepseek-v4-pro", True, latency_ms=1000)
        metric = m.get_metric("llm.deepseek.deepseek-v4-pro")
        assert metric.success_rate == 1.0

    def test_record_screening_normal(self):
        m = get_monitor()
        m.record_screening("value", count=10, total_screened=5000)
        metric = m.get_metric("screening.value")
        assert metric.success_rate == 1.0

    def test_health_summary(self):
        m = get_monitor()
        summary = m.get_health_summary()
        assert "status" in summary
        assert "metrics" in summary
        assert "recent_alerts" in summary

    def test_data_source_failure_triggers_alert(self):
        m = get_monitor()
        # Record 3 consecutive failures to trigger alert
        for _ in range(3):
            m.record_data_source("test_source", False)
        alerts = m.get_alerts()
        assert any("test_source" in a["message"] for a in alerts)

    def test_llm_failure_triggers_alert(self):
        m = get_monitor()
        for _ in range(3):
            m.record_llm_call("test_provider", "test_model", False)
        alerts = m.get_alerts()
        assert any("test_provider" in a["message"] for a in alerts)

    def test_screening_anomaly_high_ratio(self):
        m = get_monitor()
        m.record_screening("test_style", count=600, total_screened=1000)
        alerts = m.get_alerts()
        assert any("异常高" in a["message"] for a in alerts)

    def test_alert_callback(self):
        m = get_monitor()
        received = []
        m.add_alert_callback(lambda a: received.append(a))
        for _ in range(3):
            m.record_data_source("callback_test_source", False)
        assert len(received) > 0
