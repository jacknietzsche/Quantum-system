"""数据源基础设施 — 断路器、重试、限流、HTTP连接池

参考: quant-agents/daily_stock_analysis/data_provider/ 的架构设计
- CircuitBreaker: 完整状态机 (CLOSED→OPEN→HALF_OPEN)
- 指数退避重试 (tenacity风格, 无额外依赖)
- httpx连接池 (取代 urllib.request 的单次连接)
- 错误分类: 瞬态 vs 永久 vs 限流
"""

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from shared.logging import emit_log

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# -- Error hierarchy --
# ════════════════════════════════════════════════════════════


class DataSourceError(Exception):
    """数据源异常基类"""

    def __init__(self, message: str, source: str = "", method: str = ""):
        self.source = source
        self.method = method
        super().__init__(f"[{source}] {message}")


class TransientError(DataSourceError):
    """瞬态错误 — 可重试 (网络波动、超时、服务暂时不可用)"""


class RateLimitError(TransientError):
    """限流错误 — 需更长退避"""


class PermanentError(DataSourceError):
    """永久错误 — 快速失败 (配置错误、格式变更、不支持的接口)"""


# ════════════════════════════════════════════════════════════
# -- Circuit Breaker --
# ════════════════════════════════════════════════════════════


class CircuitState:
    CLOSED = "closed"  # 正常工作
    OPEN = "open"  # 熔断开启
    HALF_OPEN = "half_open"  # 试探恢复


@dataclass
class CircuitBreakerStats:
    """断路器统计"""

    state: str = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    success_count: int = 0
    total_calls: int = 0
    last_success_time: float = 0.0
    consecutive_successes: int = 0


class CircuitBreaker:
    """断路器 — 完整状态机

    状态转换:
        CLOSED ──连续 N 次失败──→ OPEN
        OPEN   ──冷却超时──────→ HALF_OPEN
        HALF_OPEN ──成功──────→ CLOSED
        HALF_OPEN ──失败──────→ OPEN

    参考: daily_stock_analysis/data_provider/realtime_types.py
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: int = 300,
        half_open_max_calls: int = 1,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        self._stats = CircuitBreakerStats()
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    def peek_available(self) -> bool:
        """只读检查: 当前状态是否允许请求 (不消耗探针, 不转换状态)"""
        with self._lock:
            if self._stats.state == CircuitState.CLOSED:
                return True
            if self._stats.state == CircuitState.OPEN:
                elapsed = time.time() - self._stats.last_failure_time
                return elapsed > self.cooldown_seconds
            # HALF_OPEN: probe slot available
            return self._half_open_calls < self.half_open_max_calls

    def try_acquire(self) -> bool:
        """尝试获取执行许可: 状态转换 + 探针槽位消耗

        - CLOSED → 直接允许
        - OPEN 且冷却已过 → HALF_OPEN + 消耗探针
        - HALF_OPEN → 消耗探针槽位
        - 无可用探针 → 返回 False
        """
        with self._lock:
            if self._stats.state == CircuitState.CLOSED:
                return True
            if self._stats.state == CircuitState.OPEN:
                elapsed = time.time() - self._stats.last_failure_time
                if elapsed > self.cooldown_seconds:
                    self._stats.state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(f"[CB] {self.name} OPEN→HALF_OPEN (冷却{self.cooldown_seconds}s后)")
                    self._half_open_calls += 1
                    return True
                return False
            # HALF_OPEN: consume probe slot
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self):
        """记录成功"""
        with self._lock:
            self._stats.total_calls += 1
            self._stats.success_count += 1
            self._stats.last_success_time = time.time()
            self._stats.failure_count = 0
            self._stats.consecutive_successes += 1
            if (
                self._stats.state == CircuitState.HALF_OPEN
                and self._stats.consecutive_successes >= self.success_threshold
            ):
                self._stats.state = CircuitState.CLOSED
                self._half_open_calls = 0
                logger.info(
                    f"[CB] {self.name} HALF_OPEN→CLOSED (连续{self.success_threshold}次成功)"
                )

    def record_failure(self):
        """记录失败"""
        with self._lock:
            self._stats.total_calls += 1
            self._stats.failure_count += 1
            self._stats.last_failure_time = time.time()
            self._stats.consecutive_successes = 0
            if self._stats.state == CircuitState.HALF_OPEN:
                self._stats.state = CircuitState.OPEN
                self._half_open_calls = 0
                logger.warning(f"[CB] {self.name} HALF_OPEN→OPEN (探测失败)")
            elif self._stats.failure_count >= self.failure_threshold:
                self._stats.state = CircuitState.OPEN
                self._half_open_calls = 0
                logger.warning(
                    f"[CB] {self.name} CLOSED→OPEN (连续{self._stats.failure_count}次失败)"
                )

    def reset(self):
        """重置为初始状态"""
        with self._lock:
            self._stats = CircuitBreakerStats()
            self._half_open_calls = 0

    def status_dict(self) -> dict:
        """返回状态字典 (供API使用)"""
        with self._lock:
            state = self._stats.state
            failures = self._stats.failure_count
            total_calls = self._stats.total_calls
            successes = self._stats.success_count
            last_fail = self._stats.last_failure_time
        # 锁外调用 peek_available 避免重入锁
        available = self.peek_available()
        cooldown_remaining = (
            max(0, self.cooldown_seconds - (time.time() - last_fail))
            if state == CircuitState.OPEN
            else 0
        )
        return {
            "name": self.name,
            "state": state,
            "failures": failures,
            "total_calls": total_calls,
            "successes": successes,
            "available": available,
            "cooldown_remaining": cooldown_remaining,
        }


# ════════════════════════════════════════════════════════════
#  HTTP Client Pool
# ════════════════════════════════════════════════════════════


class HttpClientPool:
    """httpx 连接池管理器

    取代 urllib.request 的单次连接模式:
    - 连接复用 (keep-alive)
    - 超时控制
    - 重试适配器
    - User-Agent 轮换
    """

    _instances: ClassVar[dict[str, "HttpClientPool"]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    _USER_AGENTS: ClassVar[list[str]] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    ]

    def __init__(
        self,
        name: str = "default",
        timeout: float = 15.0,
        max_connections: int = 20,
        max_keepalive: int = 10,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ):
        self.name = name
        self._timeout = timeout
        self._base_headers = headers or {}
        self._base_cookies = cookies or {}
        self._client: httpx.Client | None = None
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
        )
        self._ua_index = 0

    @classmethod
    def pool_stats(cls) -> dict:
        """返回所有连接池的配置统计"""
        pools = cls._instances or {}
        return {
            name: {
                "name": pool.name,
                "max_connections": pool._limits.max_connections,
                "max_keepalive": pool._limits.max_keepalive_connections,
                "timeout": pool._timeout,
                "client_active": pool._client is not None,
            }
            for name, pool in pools.items()
        }

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                limits=self._limits,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    def request(
        self,
        method: str,
        url: str,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> httpx.Response:
        """执行HTTP请求,自动注入 User-Agent 和基础 headers"""
        client = self._get_client()

        merged_headers = dict(self._base_headers)
        if headers:
            merged_headers.update(headers)
        merged_headers.setdefault("User-Agent", self._next_ua())
        if "Referer" not in merged_headers:
            merged_headers.setdefault("Referer", "https://finance.sina.com.cn")

        kwargs["headers"] = merged_headers
        if self._base_cookies:
            kwargs.setdefault("cookies", self._base_cookies)

        return client.request(method, url, timeout=timeout or self._timeout, **kwargs)

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def _next_ua(self) -> str:
        ua = self._USER_AGENTS[self._ua_index % len(self._USER_AGENTS)]
        self._ua_index += 1
        return ua

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    @classmethod
    def get_pool(cls, name: str = "default", **kwargs) -> "HttpClientPool":
        """获取或创建命名连接池 (单例)"""
        with cls._lock:
            if name not in cls._instances:
                cls._instances[name] = cls(name=name, **kwargs)
            return cls._instances[name]

    @classmethod
    def close_all(cls):
        """关闭所有连接池"""
        with cls._lock:
            if cls._instances:
                for pool in cls._instances.values():
                    pool.close()
                cls._instances.clear()


# ════════════════════════════════════════════════════════════
# -- Retry helper (tenacity style, no extra deps) --
# ════════════════════════════════════════════════════════════


def classify_error(error: Exception, source: str = "") -> DataSourceError:  # noqa: PLR0911
    """将异常分类为 DataSourceError 子类"""
    msg = str(error)

    if isinstance(error, httpx.TimeoutException):
        return TransientError(f"连接超时: {msg}", source)
    if isinstance(error, httpx.ConnectError):
        return TransientError(f"连接失败: {msg}", source)
    if isinstance(error, httpx.RemoteProtocolError):
        return TransientError(f"协议错误: {msg}", source)
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 429:
            return RateLimitError(f"限流 (429): {msg}", source)
        if status in (502, 503, 504):
            return TransientError(f"服务暂时不可用 ({status}): {msg}", source)
        if status in (401, 403):
            return PermanentError(f"认证/权限错误 ({status}): {msg}", source)
        if status == 404:
            return PermanentError(f"接口不存在 (404): {msg}", source)
        return TransientError(f"HTTP {status}: {msg}", source)
    if isinstance(error, ConnectionError):
        return TransientError(f"连接错误: {msg}", source)
    if isinstance(error, TimeoutError):
        return TransientError(f"超时: {msg}", source)

    # Fallback: unknown error treated as transient
    return TransientError(f"未知错误: {msg[:120]}", source)


def retry_with_backoff(
    fn: Callable,
    max_retries: int = 2,
    base_delay: float = 1.5,
    max_delay: float = 30.0,
    timeout: float | None = None,
) -> Any:
    """指数退避重试

    专为数据源HTTP调用设计:
    - 仅重试 TransientError / RateLimitError
    - PermanentError 立即抛出
    - 指数退避 + jitter
    """
    import random

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except RateLimitError:
            # Rate limit: longer backoff + jitter
            delay = min(base_delay * (4**attempt), max_delay)
            jitter = delay * 0.1 * (2 * random.random() - 1)  # noqa: S311
            last_exc = "rate_limit"
            if attempt < max_retries:
                logger.debug(f"[Retry] 限流, 等待 {delay + jitter:.1f}s (第{attempt + 1}次)")
                time.sleep(delay + jitter)
        except TransientError:
            delay = min(base_delay * (2**attempt), max_delay)
            jitter = delay * 0.1 * (2 * random.random() - 1)  # noqa: S311
            last_exc = "transient"
            if attempt < max_retries:
                logger.debug(f"[Retry] 瞬态错误, 等待 {delay + jitter:.1f}s (第{attempt + 1}次)")
                time.sleep(delay + jitter)
        except PermanentError:
            raise
        except Exception as e:
            # 未知异常: 按 TransientError 处理
            delay = min(base_delay * (2**attempt), max_delay)
            jitter = delay * 0.1 * (2 * random.random() - 1)  # noqa: S311
            last_exc = str(e)[:80]
            if attempt < max_retries:
                logger.debug(f"[Retry] 未知异常, 等待 {delay + jitter:.1f}s (第{attempt + 1}次)")
                time.sleep(delay + jitter)

    raise TransientError(f"重试{max_retries}次后仍然失败: {last_exc}")


# ════════════════════════════════════════════════════════════
# -- Source Adapter base --
# ════════════════════════════════════════════════════════════


class SourceAdapter:
    """数据源适配器基类

    每个数据源实现此接口, 注册到 MarketDataProvider。
    参考: daily_stock_analysis/data_provider/base.py
    """

    name: str = ""  # 唯一标识符
    priority: int = 99  # 优先级 (越小越优先)
    timeout: float = 10.0  # 默认超时

    def __init__(self):
        if not self.name:
            raise ValueError("SourceAdapter 必须设置 name")
        self._cb = CircuitBreaker(name=self.name)
        self._http: HttpClientPool | None = None

    @property
    def http(self) -> HttpClientPool:
        if self._http is None:
            self._http = HttpClientPool.get_pool(f"src_{self.name}", timeout=self.timeout)
        return self._http

    @property
    def cb(self) -> CircuitBreaker:
        return self._cb

    # ── 各数据方法: 默认返回 _NOT_SUPPORTED ──

    def fetch_indices(self) -> dict | None:
        """获取指数数据"""
        return None

    def fetch_north_flow(self) -> dict | None:
        """获取北向资金"""
        return None

    def fetch_stock_spot(self):
        """获取全市场实时快照 (DataFrame)"""
        return

    def fetch_full_spot(self):
        """获取全A股快照 (DataFrame)"""
        return self.fetch_stock_spot()

    def fetch_etf_spot(self):
        """获取ETF/LOF快照 (DataFrame)"""
        return

    def fetch_kline(self, code: str, days: int = 90):
        """获取个股日K线"""
        return

    def fetch_basic(self, code: str) -> dict | None:
        """获取个股基本面"""
        return None

    def fetch_hot_stocks(self, sort: str = "change_pct", limit: int = 100) -> list | None:
        """获取热门股票"""
        return None

    # ── 健康检查 ──

    def test_connect(self) -> bool:
        """测试连接是否可用 (默认实现)"""
        try:
            result = self.fetch_indices()
            return result is not None
        except Exception as e:
            emit_log("WARNING", "source_base", f"Operation failed: {str(e)[:100]}")
            return False


# ════════════════════════════════════════════════════════════
#  Rate Limiter (信号量 + 僵尸回收)
# ════════════════════════════════════════════════════════════


class RateLimiter:
    """API频率限制器 — 信号量 + 僵尸线程回收

    参考: TradingAgents-AShare _AkshareLock
    """

    STALE_TIMEOUT = 120

    def __init__(self, total: int = 5, acquire_timeout: float = 15.0, name: str = ""):
        self._sem = threading.Semaphore(total)
        self._mu = threading.Lock()
        self._holders: dict[int, float] = {}
        self._acquire_timeout = acquire_timeout
        self._total = total
        self.name = name

    def _reclaim_stale(self) -> int:
        now = time.time()
        reclaimed = 0
        with self._mu:
            stale = [tid for tid, ts in self._holders.items() if now - ts > self.STALE_TIMEOUT]
            for tid in stale:
                del self._holders[tid]
                reclaimed += 1
        for _ in range(reclaimed):
            with contextlib.suppress(ValueError):
                self._sem.release()
        return reclaimed

    def acquire(self) -> bool:
        self._reclaim_stale()
        try:
            if self._sem.acquire(timeout=self._acquire_timeout):
                with self._mu:
                    self._holders[threading.get_ident()] = time.time()
                return True
        except Exception as e:
            emit_log("WARNING", "source_base", f"Operation failed: {str(e)[:100]}")
        return False

    def release(self):
        tid = threading.get_ident()
        with self._mu:
            self._holders.pop(tid, None)
        with contextlib.suppress(ValueError):
            self._sem.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
