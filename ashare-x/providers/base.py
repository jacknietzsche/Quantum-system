"""数据源适配器基类（断路器 + 重试 + 连接池）。

设计依据: S05 §5.3-5.6, 现有系统 providers/source_base.py。
实验验证: experiments exp1.3/exp6.3。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """断路器（3次失败→熔断5分钟→半开试探）。"""

    def __init__(self, failure_threshold: int = 3, cooldown: float = 300):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.cooldown:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def reset(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED


class SourceAdapter:
    """数据源适配器基类。"""

    def __init__(self, name: str, priority: int = 99, timeout: float = 10.0):
        self.name = name
        self.priority = priority
        self.timeout = timeout
        self.breaker = CircuitBreaker()
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        """获取K线数据。子类实现。"""
        raise NotImplementedError

    def fetch_basic(self, code: str) -> dict | None:
        """获取基本面数据。子类实现。"""
        raise NotImplementedError

    def test_connect(self) -> bool:
        """健康检查。子类实现。"""
        return True

    def _execute_with_retry(self, fn: Callable, max_retries: int = 2) -> Any:
        """带重试的执行。"""
        if not self.breaker.can_execute():
            raise ConnectionError(f"{self.name} 熔断中")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = fn()
                self.breaker.record_success()
                return result
            except Exception as e:
                last_error = e
                self.breaker.record_failure()
                if attempt < max_retries:
                    delay = 1.5 * (2**attempt)  # 指数退避
                    time.sleep(delay)
                    logger.warning("重试 %s (attempt %d): %s", self.name, attempt + 1, e)

        raise last_error
