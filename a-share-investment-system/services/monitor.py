"""运行时监控服务 — 数据源可用性 + LLM成功率 + 选股异常检测"""

import contextlib
import threading
import time
from collections import deque
from datetime import datetime

from shared.logging import emit_log


class HealthMetrics:
    """单项健康指标追踪器"""

    def __init__(self, name: str, window_size: int = 100):
        self.name = name
        self._window: deque[dict] = deque(maxlen=window_size)
        self._last_success: float | None = None
        self._last_failure: float | None = None
        self._consecutive_failures = 0

    def record(self, success: bool, latency_ms: float = 0, detail: str = ""):
        entry = {
            "ts": time.time(),
            "ok": success,
            "latency_ms": latency_ms,
            "detail": detail[:200],
        }
        self._window.append(entry)
        if success:
            self._last_success = time.time()
            self._consecutive_failures = 0
        else:
            self._last_failure = time.time()
            self._consecutive_failures += 1

    @property
    def success_rate(self) -> float:
        if not self._window:
            return 1.0
        ok = sum(1 for e in self._window if e["ok"])
        return ok / len(self._window)

    @property
    def avg_latency_ms(self) -> float:
        if not self._window:
            return 0
        lats = [e["latency_ms"] for e in self._window if e["latency_ms"] > 0]
        return sum(lats) / len(lats) if lats else 0

    @property
    def is_healthy(self) -> bool:
        return self.success_rate >= 0.8 and self._consecutive_failures < 5

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "is_healthy": self.is_healthy,
            "consecutive_failures": self._consecutive_failures,
            "total_requests": len(self._window),
            "last_success": self._last_success,
            "last_failure": self._last_failure,
        }


class RuntimeMonitor:
    """运行时监控器 — 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._metrics: dict[str, HealthMetrics] = {}
        self._alerts: deque = deque(maxlen=200)
        self._alert_callbacks: list = []

    def get_metric(self, name: str) -> HealthMetrics:
        if name not in self._metrics:
            self._metrics[name] = HealthMetrics(name)
        return self._metrics[name]

    def record_data_source(self, source: str, success: bool, latency_ms: float = 0):
        """记录数据源调用结果"""
        metric = self.get_metric(f"data_source.{source}")
        metric.record(success, latency_ms)
        if not success and metric.consecutive_failures >= 3:
            self._fire_alert(
                "DATA_SOURCE_DOWN",
                f"数据源 {source} 连续{metric.consecutive_failures}次失败",
                "HIGH",
            )

    def record_llm_call(self, provider: str, model: str, success: bool, latency_ms: float = 0):
        """记录LLM调用结果"""
        metric = self.get_metric(f"llm.{provider}.{model}")
        metric.record(success, latency_ms)
        if not success and metric.consecutive_failures >= 3:
            self._fire_alert(
                "LLM_UNAVAILABLE",
                f"LLM {provider}/{model} 连续{metric.consecutive_failures}次失败",
                "HIGH",
            )

    def record_screening(self, style: str, count: int, total_screened: int):
        """记录选股结果，检测异常"""
        metric = self.get_metric(f"screening.{style}")
        metric.record(True)
        if total_screened > 0:
            ratio = count / total_screened
            if ratio > 0.5:
                self._fire_alert(
                    "SCREENING_ANOMALY",
                    f"选股[{style}]通过率异常高: {count}/{total_screened}={ratio:.1%}",
                    "MEDIUM",
                )
            elif ratio < 0.001 and total_screened > 100:
                self._fire_alert(
                    "SCREENING_ANOMALY",
                    f"选股[{style}]通过率异常低: {count}/{total_screened}={ratio:.3%}",
                    "MEDIUM",
                )

    def _fire_alert(self, alert_type: str, message: str, severity: str):
        alert = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": alert_type,
            "message": message,
            "severity": severity,
        }
        self._alerts.append(alert)
        emit_log("WARNING", "monitor", f"[{severity}] {alert_type}: {message}")
        for cb in self._alert_callbacks:
            with contextlib.suppress(Exception):
                cb(alert)

    def add_alert_callback(self, callback):
        self._alert_callbacks.append(callback)

    def get_health_summary(self) -> dict:
        """获取全局健康摘要"""
        all_metrics = {name: m.to_dict() for name, m in self._metrics.items()}
        unhealthy = [name for name, m in self._metrics.items() if not m.is_healthy]
        return {
            "status": "healthy" if not unhealthy else "degraded",
            "unhealthy_components": unhealthy,
            "metrics": all_metrics,
            "recent_alerts": list(self._alerts)[-10:],
            "total_alerts": len(self._alerts),
        }

    def get_alerts(self, limit: int = 50) -> list[dict]:
        return list(self._alerts)[-limit:]


def get_monitor() -> RuntimeMonitor:
    return RuntimeMonitor()
