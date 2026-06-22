"""数据源健康检查。

设计依据: experiments exp11.3。
检查各数据源的可用性和延迟。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class DataProviderHealth:
    """数据源健康检查管理器。"""

    def __init__(self):
        self.providers: dict[str, dict] = {}

    def check(self, name: str, check_fn: Callable) -> dict:
        """检查数据源健康状态。"""
        start = time.time()
        try:
            check_fn()
            latency = (time.time() - start) * 1000
            self.providers[name] = {
                "status": "healthy",
                "latency_ms": round(latency, 1),
                "last_check": datetime.now().isoformat(),
                "error": None,
            }
        except Exception as e:
            latency = (time.time() - start) * 1000
            self.providers[name] = {
                "status": "unhealthy",
                "latency_ms": round(latency, 1),
                "last_check": datetime.now().isoformat(),
                "error": str(e),
            }
        return self.providers[name]

    def get_status(self) -> dict:
        """获取所有数据源状态。"""
        return self.providers.copy()

    def get_healthy_providers(self) -> list[str]:
        """获取健康的数据源列表。"""
        return [name for name, info in self.providers.items() if info["status"] == "healthy"]
