"""AShare-X 领域服务基类"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ServiceResult:
    """所有领域服务的统一返回类型"""

    status: Literal["ok", "degraded", "error"]
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: dict[str, Any] | None = None, **metrics) -> "ServiceResult":
        return cls(status="ok", data=data or {}, metrics=metrics)

    @classmethod
    def degraded(cls, data: dict[str, Any], errors: list[str], **metrics) -> "ServiceResult":
        return cls(status="degraded", data=data, errors=errors, metrics=metrics)

    @classmethod
    def error(
        cls, errors: list[str], data: dict[str, Any] | None = None, **metrics
    ) -> "ServiceResult":
        return cls(status="error", data=data or {}, errors=errors, metrics=metrics)


class BaseService:
    """所有领域服务的基类"""

    def __init__(self):
        self._call_count = 0
        self._total_elapsed_ms = 0.0

    def health_check(self) -> bool:
        """子类可重写,默认返回True"""
        return True

    def get_metrics(self) -> dict[str, float]:
        return {
            "call_count": self._call_count,
            "total_elapsed_ms": self._total_elapsed_ms,
        }

    def _track(self, result: ServiceResult, elapsed_ms: float) -> ServiceResult:
        self._call_count += 1
        self._total_elapsed_ms += elapsed_ms
        result.metrics["elapsed_ms"] = elapsed_ms
        return result
