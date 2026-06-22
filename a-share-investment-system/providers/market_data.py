"""多源日频数据提供者 — SQLite优先 + 6源降级 (v5.3: concurrency lock + retry backoff)"""

import contextlib
import json
import logging
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta

from shared.logging import emit_log

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_NOT_SUPPORTED = object()  # 方法不支持(非失败, 不触发断路器)

# 延迟导入 TushareAdapter (由 _get_tushare_adapter 按需创建)
_tushare_adapter = None

_API_TIMEOUT = 15
_DEGRADED_TIMEOUT = 3  # 已知不可用源的快速超时
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 1.5

# 已知不可用源 — 当前网络环境无法连接
_KNOWN_DEAD_SOURCES = {"tickflow", "baostock", "eastmoney", "efinance", "hot_rank", "board_rank"}

# Set NO_PROXY early for domestic sites to prevent requests/httpx from using system proxy
# This must happen before any library that reads these env vars is imported
_DOMESTIC_NO_PROXY = "localhost,127.0.0.1,push2.eastmoney.com,qt.gtimg.cn,hq.sinajs.cn,finance.sina.com.cn,money.finance.sina.com.cn,vip.stock.finance.sina.com.cn,data.eastmoney.com,datacenter-web.eastmoney.com,api.tushare.pro,tushare.pro,web.ifzq.gtimg.cn,.eastmoney.com,.sina.com.cn,.gtimg.cn"
os.environ.setdefault("NO_PROXY", _DOMESTIC_NO_PROXY)
os.environ.setdefault("no_proxy", _DOMESTIC_NO_PROXY)

_SECTOR_FIELD_MAP = {
    "板块名称": "name",
    "涨跌幅": "change_pct",
    "换手率": "turnover",
    "排名": "rank",
    "最新价": "price",
    "成交额": "amount",
    "涨跌额": "change_amt",
    "成交量": "volume",
    "市盈率-动态": "pe_ratio",
    "代码": "stock_code",
    "名称": "stock_name",
}

# Ensure .env is loaded before reading env vars (Config may not be instantiated yet)
_ENV_FILE_2 = os.path.join(_PROJECT_ROOT, "config", ".env")
if os.path.exists(_ENV_FILE_2):
    with open(_ENV_FILE_2, encoding="utf-8") as _f:
        for _raw_line in _f:
            _line = _raw_line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_TICKFLOW_TOKEN = os.environ.get("TICKFLOW_API_KEY", "")
_TICKFLOW_BASE = os.environ.get("TICKFLOW_BASE_URL", "") or "https://api.tickflow.com/v1"

# ════════════════════════════════════════════
#  并发锁(参考 TradingAgents-AShare _AkshareLock)
# ════════════════════════════════════════════


class _ApiRateLimiter:
    """API频率限制器 — Semaphore + 僵尸线程回收"""

    STALE_TIMEOUT = 120

    def __init__(self, total: int = 5, scheduled_max: int = 3):
        self._total = threading.Semaphore(total)
        self._scheduled = threading.Semaphore(scheduled_max)
        self._mu = threading.Lock()
        self._holders: dict[int, float] = {}

    def _reclaim_stale(self) -> int:
        now = time.time()
        reclaimed = 0
        with self._mu:
            stale = [tid for tid, ts in self._holders.items() if now - ts > self.STALE_TIMEOUT]
            for tid in stale:
                del self._holders[tid]
                reclaimed += 1
        if reclaimed:
            for _ in range(reclaimed):
                with contextlib.suppress(ValueError):
                    self._total.release()
                with contextlib.suppress(ValueError):
                    self._scheduled.release()
        return reclaimed

    def acquire(self, is_scheduled: bool = False) -> bool:
        self._reclaim_stale()
        sem = self._scheduled if is_scheduled else self._total
        try:
            if sem.acquire(timeout=15):
                if not is_scheduled:
                    with contextlib.suppress(Exception):
                        self._total.acquire(timeout=0.1)
                with self._mu:
                    self._holders[threading.get_ident()] = time.time()
                return True
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return False

    def release(self, is_scheduled: bool = False):
        tid = threading.get_ident()
        with self._mu:
            if tid in self._holders:
                del self._holders[tid]
        with contextlib.suppress(ValueError):
            self._total.release()
        if is_scheduled:
            with contextlib.suppress(ValueError):
                self._scheduled.release()


def _load_rate_limits() -> tuple:
    """从 config 读取速率限制参数"""
    try:
        from shared.config import Config

        cfg = Config().get("data.rate_limit", {})
        return cfg.get("total", 5), cfg.get("scheduled", 3)
    except Exception as e:
        emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return 5, 3


_API_TOTAL, _API_SCHEDULED = _load_rate_limits()
_API_LOCK = _ApiRateLimiter(total=_API_TOTAL, scheduled_max=_API_SCHEDULED)

# ????????????????????????????????????????????
#  Proxy auto-activation (Hiddify)
# ????????????????????????????????????????????


def _get_proxy_opener():
    """Return a urllib opener with proxy if PROXY_ENABLED=true and proxy is reachable.
    Does NOT set HTTP_PROXY/HTTPS_PROXY env vars — those break requests/httpx globally.
    yfinance_src handles its own proxy via _proxy_env() context manager."""
    import socket

    proxy_url = os.environ.get("PROXY_URL", "http://127.0.0.1:12334")
    proxy_enabled = os.environ.get("PROXY_ENABLED", "false").lower() in ("true", "1", "yes")
    if not proxy_enabled:
        return None
    # Quick connectivity check (0.3s timeout)
    try:
        host, port = proxy_url.replace("http://", "").replace("https://", "").split(":")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        sock.connect((host, int(port)))
        sock.close()
        # urllib-level proxy opener — only used by _urlopen() for non-domestic calls
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
        logger.info("[MarketData] Proxy activated: %s (urllib only, no env vars set)", proxy_url)
        return opener
    except (TimeoutError, ConnectionRefusedError, OSError):
        logger.debug("[MarketData] Proxy not reachable: %s, using direct", proxy_url)
        return None


_proxy_opener = _get_proxy_opener()

_DOMESTIC_HOSTS = {
    "push2.eastmoney.com",
    "qt.gtimg.cn",
    "hq.sinajs.cn",
    "web.ifzq.gtimg.cn",
    "finance.sina.com.cn",
    "money.finance.sina.com.cn",
    "vip.stock.finance.sina.com.cn",
    "data.eastmoney.com",
    "datacenter-web.eastmoney.com",
    "api.tushare.pro",
    "tushare.pro",
}

# No-proxy opener for domestic sites — uses standard urllib stack (reliable SSL)
_domestic_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _domestic_urlopen(req, timeout=15):
    """urllib-based connection for domestic sites — bypasses system proxy, uses standard SSL
    stack."""
    return _domestic_opener.open(req, timeout=timeout)


def _urlopen(req, timeout=15):
    """urlopen with dual-mode fallback:
    Always try direct first (fast for domestic APIs).
    If direct fails AND proxy is available, retry via proxy.
    仅允许 http/https scheme，防止 file:/custom scheme 被意外打开。
    """
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    try:
        return _domestic_opener.open(req, timeout=timeout)
    except Exception as direct_err:
        if _proxy_opener:
            try:
                return _proxy_opener.open(req, timeout=timeout)
            except Exception as proxy_err:
                logger.debug("proxy open failed, will raise direct error: %s", proxy_err)
        raise direct_err


def _latest_trade_date() -> str:
    """17:00后返回今天,否则返回昨天"""
    now = datetime.now()
    if now.hour >= 17:
        return now.strftime("%Y-%m-%d")
    return (now - timedelta(days=1)).strftime("%Y-%m-%d")


def _call_with_retry(fn, timeout=_API_TIMEOUT, max_retries=_MAX_RETRIES):
    """指数退避重试 — 参考 daily_stock_analysis 的 retry pattern"""
    for attempt in range(max_retries + 1):
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(fn)
            result = future.result(timeout=timeout)
            if result is not None:
                return result
        except FuturesTimeoutError:
            pass
        except Exception as e:
            logger.debug("[MarketData] retry attempt %d error: %s", attempt, str(e)[:80])
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if attempt < max_retries:
            wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
            time.sleep(wait)

    return None


# ════════════════════════════════════════════
#  断路器(参考 daily_stock_analysis circuit breaker)
# ════════════════════════════════════════════


class _CircuitBreaker:
    """单源断路器 — 连续失败N次后自动跳过,冷却期后探针检测恢复"""

    FAIL_THRESHOLD = 3  # 连续失败3次触发断路
    COOLDOWN_SECONDS = 60  # 1分钟冷却期(原300s,减小以快速恢复)
    HALF_OPEN_PROBE = 1  # 冷却后最多试探1次

    def __init__(self, name: str):
        self.name = name
        self._failures = 0
        self._last_fail_time = 0.0
        self._state = "closed"  # closed → open → half_open → closed

    def record_success(self):
        self._failures = max(0, self._failures - 1)
        if self._state == "half_open":
            logger.info("[CB] %s CLOSED (recovered)", self.name)
        self._state = "closed"

    def record_failure(self):
        self._failures += 1
        self._last_fail_time = time.time()
        if self._failures >= self.FAIL_THRESHOLD:
            if self._state != "open":
                logger.info(
                    "[CB] %s OPEN after %d failures (cooldown=%ds)",
                    self.name,
                    self._failures,
                    self.COOLDOWN_SECONDS,
                )
            self._state = "open"

    def is_available(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.time() - self._last_fail_time > self.COOLDOWN_SECONDS:
                self._state = "half_open"
                logger.info("[CB] %s HALF_OPEN (probe allowed)", self.name)
                return True  # 允许探测
            return False
        return True  # half_open: 允许一次探测

    @property
    def status(self) -> str:
        return self._state


class MarketDataProvider:
    """多源降级调度器 — 每个方法通过 _try_sources 按优先级尝试"""

    def __init__(self):
        self._failed_sources = {}
        self._ok_sources = {}
        self._breakers = {}
        self._cache = None
        self._reported_methods = set()

    # ═══════════════════════════════════════════
    #  公开接口
    # ═══════════════════════════════════════════

    def get_indices(self) -> dict:
        """获取4个主要指数日频数据"""
        return self._try_sources("fetch_indices") or {
            "indices": {},
            "breadth": {},
            "sectors": [],
            "data_time": "",
        }

    def get_north_flow(self) -> dict:
        """获取北向资金净流入"""
        return self._try_sources("fetch_north_flow") or {}

    def get_stock_spot(self):
        """获取全市场实时快照(DataFrame)"""
        return self._try_sources("fetch_stock_spot")

    def get_hot_stocks(self, sort: str = "change_pct", limit: int = 100) -> list:
        """获取热门股票TOP N — 东方财富优先,Sina降级"""
        # Try EastMoney first (fastest, most reliable)
        result = self._source_eastmoney_hot(sort, limit)
        if result:
            return result
        # Fallback: use spot data sorted locally
        spot = self.get_stock_spot()
        if spot is not None and hasattr(spot, "columns") and not spot.empty:
            col_map = {"change_pct": "change_pct", "turnover": "amount", "volume": "volume"}
            sort_col = col_map.get(sort, "change_pct")
            if sort_col in spot.columns:
                top = spot.nlargest(limit, sort_col)
                result = []
                for _, r in top.iterrows():
                    result.append(
                        {
                            "stock_code": str(r.get("stock_code", r.get("代码", ""))),
                            "stock_name": str(r.get("stock_name", r.get("名称", ""))),
                            "price": float(r.get("price", r.get("最新价", 0)) or 0),
                            "change_pct": float(r.get("change_pct", r.get("涨跌幅", 0)) or 0),
                            "change_amt": float(r.get("change_amt", r.get("涨跌额", 0)) or 0),
                            "volume": float(r.get("volume", r.get("成交量", 0)) or 0),
                            "amount": float(r.get("amount", r.get("成交额", 0)) or 0),
                            "turnover_rate": float(r.get("turnover_rate", r.get("换手率", 0)) or 0),
                            "pe_ratio": float(r.get("pe_ratio", r.get("市盈率-动态", 0)) or 0),
                        }
                    )
                return result
        return None

    def get_stock_kline(self, code: str, days: int = 90):
        """获取个股日K线"""
        return self._try_sources("fetch_kline", code, days)

    def get_stock_basic(self, code: str) -> dict:
        """获取个股基本面"""
        return self._try_sources("fetch_basic", code) or {}

    def get_hot_stocks_eastmoney(self, limit: int = 100) -> list:
        """EastMoney热榜 — 返回 code list"""
        return self._try_sources("fetch_hot_stocks_em", limit) or []

    def get_hot_stocks_xueqiu(self) -> list:
        """雪球热榜 — 返回 code list"""
        return self._try_sources("fetch_hot_stocks_xq") or []

    def get_full_market_spot(self):
        """全市场快照 (DataFrame) — 用于获取全A股列表"""
        return self._try_sources("fetch_full_spot")

    # ═══════════════════════════════════════════
    #  降级调度
    # ═══════════════════════════════════════════

    def _try_sources(self, method: str, *args):
        from shared.config import Config

        cfg = Config()
        preferred = cfg.get("data.fallback_chain", []) or []
        try:
            from providers.sources.tushare import _resolve_token

            tushare_ready = bool(_resolve_token())
        except Exception:
            tushare_ready = False
        available_map = {
            "eastmoney": ("eastmoney", self._source_eastmoney),
            "tencent": ("tencent", self._source_tencent),
            "sina": ("sina", self._source_sina),
            "akshare": ("akshare", self._source_akshare),
            "tushare": ("tushare", self._source_tushare),
            "baostock": ("baostock", self._source_baostock),
            "efinance": ("efinance", self._source_efinance),
            "tickflow": ("tickflow", self._source_tickflow),
            "yfinance": ("yfinance", self._source_yfinance),
            "adata": ("adata", self._source_adata),
            "zzshare": ("zzshare", self._source_zzshare),
            "sina_financial": (
                "sina_financial",
                lambda m, *a: getattr(self, "_NOT_SUPPORTED", None),
            ),
            "zt_pool": ("zt_pool", lambda m, *a: getattr(self, "_NOT_SUPPORTED", None)),
        }
        seen = set()
        sources = []
        for name in preferred:
            entry = available_map.get(name)
            if entry and entry[0] not in seen:
                sources.append(entry)
                seen.add(entry[0])
        for entry in [
            ("tencent", self._source_tencent),
            ("sina", self._source_sina),
            ("akshare", self._source_akshare),
            ("tushare", self._source_tushare),
            ("baostock", self._source_baostock),
            ("efinance", self._source_efinance),
            ("eastmoney", self._source_eastmoney),
            ("tickflow", self._source_tickflow),
            ("yfinance", self._source_yfinance),
            ("adata", self._source_adata),
            ("zzshare", self._source_zzshare),
        ]:
            if entry[0] not in seen:
                sources.append(entry)
                seen.add(entry[0])
        if not tushare_ready:
            sources = [(n, fn) for (n, fn) in sources if n != "tushare"]
        sources = [(n, fn) for (n, fn) in sources if n not in _KNOWN_DEAD_SOURCES or n == "tushare"]
        failed_set = self._failed_sources.setdefault(method, set())
        ok_set = self._ok_sources.setdefault(method, set())
        failed = []
        skipped_cb = []  # 断路器跳过的源
        ok = list(ok_set)

        for name, source_fn in sources:
            if name in failed_set:
                continue

            # 断路器检查
            cb = self._breakers.setdefault(name, _CircuitBreaker(name))
            if not cb.is_available():
                skipped_cb.append(f"{name}({cb.status})")
                continue

            # 降级源快速超时不重试
            if name in _KNOWN_DEAD_SOURCES:
                result = _call_with_retry(
                    lambda fn=source_fn: fn(method, *args), timeout=_DEGRADED_TIMEOUT, max_retries=0
                )
            else:
                result = _call_with_retry(
                    lambda fn=source_fn: fn(method, *args), timeout=_API_TIMEOUT
                )
            if result is _NOT_SUPPORTED:
                continue  # 源不支持此方法, 跳过不记录失败
            if result is not None:
                if hasattr(result, "empty"):
                    if not result.empty:
                        cb.record_success()
                        ok_set.add(name)
                        return result
                elif hasattr(result, "__len__"):
                    if len(result) > 0:
                        cb.record_success()
                        ok_set.add(name)
                        return result
                elif result:
                    cb.record_success()
                    ok_set.add(name)
                    return result

            cb.record_failure()
            failed_set.add(name)
            failed.append(name)

        # 每个method只打印一次总结
        if (failed or skipped_cb) and method not in self._reported_methods:
            self._reported_methods.add(method)
            parts = []
            if ok:
                parts.append(f"{len(ok)}/{len(sources)} OK ({chr(44).join(ok)[:30]})")
            if failed:
                parts.append(f"failed: {chr(44).join(failed[:3])}")
            if skipped_cb:
                parts.append(f"tripped: {chr(44).join(skipped_cb[:3])}")
            logger.debug("[MarketData] %s: %s", method, " | ".join(parts))
        return None

    def _try_adapters(self, method: str, *args):
        """_try_sources 的向后兼容别名 (旧测试/外部调用使用)"""
        return self._try_sources(method, *args)

    def test_all_sources(self) -> dict:
        """逐一测试每个数据源连接状态 — 轻量请求, 返回延迟+成功/失败
        全局超时: 最多测试15秒, 超时未完成的标记为timeout"""
        import threading as _th
        import time as _time

        results = {}
        tests = {
            "tencent": ("fetch_indices", self._tx_indices),
            "sina": ("fetch_indices", self._sina_indices),
            "akshare": ("fetch_indices", self._ak_indices_test),
            "tushare": ("test", self._ts_test_connect),
            "baostock": ("test", self._bs_test_connect),
            "efinance": ("test", self._ef_test_connect),
            "tickflow": ("test", self._tf_test_connect),
            "yfinance": ("basic", self._yf_test_connect),
            "adata": ("test", self._ada_test_connect),
            "zzshare": ("basic", self._zz_test_connect),
        }
        deadline = _time.time() + 15  # 全局15秒超时
        threads = {}

        def _run_test(name, method, fn):
            t0 = _time.time()
            try:
                timeout = _DEGRADED_TIMEOUT if name in _KNOWN_DEAD_SOURCES else _API_TIMEOUT
                result = _call_with_retry(
                    lambda: fn() if callable(fn) else self._try_sources(method),
                    timeout=timeout,
                    max_retries=0,
                )
                elapsed = min(round((_time.time() - t0) * 1000), 9999)
                results[name] = {
                    "ok": result is not None,
                    "latency_ms": elapsed,
                    "error": None if result is not None else "timeout",
                }
            except Exception as e:
                results[name] = {
                    "ok": False,
                    "latency_ms": min(round((_time.time() - t0) * 1000), 9999),
                    "error": str(e)[:60],
                }

        for name, (method, fn) in tests.items():
            t = _th.Thread(target=_run_test, args=(name, method, fn), daemon=True)
            threads[name] = t
            t.start()

        for name in tests:
            remaining = max(0.1, deadline - _time.time())
            threads[name].join(timeout=remaining)
            if name not in results:
                results[name] = {"ok": False, "latency_ms": 0, "error": "timeout(global)"}

        return results

    def _bs_test_connect(self):
        try:
            import baostock as bs

            lg = bs.login()
            ok = lg.error_code == "0"
            bs.logout()
            return ok
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _ef_test_connect(self):
        try:
            import json as _json

            url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=3&po=1&np=1&fltt=2&invt=2&fid=f12&fs=m:0+t:6&fields=f12,f14"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
            resp = _urlopen(req, timeout=8)
            data = _json.loads(resp.read().decode("utf-8"))
            return data.get("data", {}).get("total", 0) > 0
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _ts_test_connect(self):
        # Lightweight check: just verify tushare module loads and token is set
        try:
            import tushare as ts

            token = os.environ.get("TUSHARE_TOKEN", "")
            if not token:
                return None
            ts.set_token(token)
            pro = ts.pro_api()
            # Use a very lightweight endpoint to avoid rate limits
            return pro is not None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _tf_test_connect(self):
        try:
            import json
            import urllib.request

            req = urllib.request.Request(  # noqa: S310
                f"{_TICKFLOW_BASE}/market/spot?market=cn",
                headers={"Authorization": f"Bearer {_TICKFLOW_TOKEN}"},
            )
            resp = _urlopen(req, timeout=10)
            return json.loads(resp.read()).get("code") == 0
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _ak_indices_test(self):
        try:
            import akshare as ak

            df = ak.stock_zh_index_daily(symbol="sh000001")
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _yf_test_connect(self):
        """yfinance 连接测试 — 尝试获取贵州茅台基本信息"""
        try:
            from providers.sources.yfinance_src import YFinanceAdapter

            adapter = YFinanceAdapter()
            result = adapter.fetch_basic("600519")
            return result is not None and bool(result.get("stock_name"))
        except ImportError:
            return None
        except Exception as e:
            emit_log("WARNING", "market_data", f"yfinance test failed: {str(e)[:60]}")
            return None

    def _ada_test_connect(self):
        """adata 连接测试 — 通过指数接口验证"""
        try:
            import adata

            # 使用 adata 获取上证指数 (数据源:新浪, 不需要代理)
            df = adata.stock.info.get_dynamic_core_index()
            return df is not None and not df.empty
        except ImportError:
            return None
        except Exception as e:
            emit_log("DEBUG", "market_data", f"adata test skipped: {str(e)[:60]}")
            return None

    def _source_adata(self, method: str, *args):
        """adata 数据源 — 通过 adata 库获取指数+市场数据 (公开免费, 新浪源)"""
        try:
            import adata
        except ImportError:
            return _NOT_SUPPORTED

        try:
            if method == "fetch_indices":
                df = adata.stock.info.get_dynamic_core_index()
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    return {
                        "indices": {
                            "上证指数": {
                                "price": float(latest.get("close", 0)),
                                "change_pct": float(latest.get("changePercent", 0) or 0),
                                "amount": 0,
                            },
                        },
                        "breadth": {
                            "total": 0,
                            "up": 0,
                            "down": 0,
                            "flat": 0,
                            "limit_up": 0,
                            "limit_down": 0,
                            "up_ratio": 0,
                        },
                        "sectors": [],
                        "data_time": __import__("time").strftime("%Y-%m-%d %H:%M"),
                    }
        except Exception as e:
            emit_log("WARNING", "market_data", f"adata indices failed: {str(e)[:60]}")
        return None

    def reset_source_health(self):
        self._failed_sources = {}
        self._ok_sources = {}
        if hasattr(self, "_reported_methods"):
            self._reported_methods = set()

    def get_source_status(self) -> dict:
        """Fail-open状态:返回每个源的健康状态,消费者可根据状态做决策"""
        status = {}
        for name in [
            "tencent",
            "sina",
            "akshare",
            "tushare",
            "baostock",
            "efinance",
            "tickflow",
            "yfinance",
            "adata",
            "zzshare",
        ]:
            cb = self._breakers.get(name) if hasattr(self, "_breakers") else None
            status[name] = {
                "state": cb.status if cb else "unknown",
                "failures": cb._failures if cb else 0,
                "available": cb.is_available() if cb else True,
            }
        return status

    def reset_sources(self):
        """重置所有数据源断路器 — 启动时调用或手动恢复"""
        if hasattr(self, "_breakers"):
            for _name, cb in self._breakers.items():
                cb._failures = 0
                cb._state = "closed"
            self._failed_sources.clear()
            self._ok_sources.clear()
            self._reported_methods.clear()

    # ═══════════════════════════════════════════
    #  Source 1: AKShare
    # ═══════════════════════════════════════════

    def _source_akshare(self, method: str, *args):  # noqa: PLR0911
        # AKShare import blocks on some envs; for fetch_basic skip to Tencent/Sina
        if method == "fetch_basic":
            return None

        try:
            import akshare as ak
        except ImportError:
            return None

        if method == "fetch_indices":
            return self._ak_indices(ak)
        if method == "fetch_north_flow":
            return self._ak_north_flow(ak)
        if method == "fetch_stock_spot":
            return self._ak_spot(ak)
        if method == "fetch_kline":
            return self._ak_kline(ak, *args)
        if method == "fetch_full_spot":
            return self._ak_full_spot(ak)
        return None

    def _ak_indices(self, ak) -> dict:
        result = {
            "indices": {},
            "breadth": {
                "total": 0,
                "up": 0,
                "down": 0,
                "flat": 0,
                "limit_up": 0,
                "limit_down": 0,
                "up_ratio": 0,
            },
            "sectors": [],
            "data_time": time.strftime("%Y-%m-%d %H:%M"),
        }
        for name, code in [
            ("上证指数", "sh000001"),
            ("深证成指", "sz399001"),
            ("创业板指", "sz399006"),
            ("中证500", "sh000905"),
        ]:
            try:
                df = ak.stock_zh_index_daily(symbol=code)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["indices"][name] = {
                        "price": float(latest.get("close", 0)),
                        "change_pct": round(float(latest.get("pct_chg", 0) or 0), 2),
                        "amount": float(latest.get("amount", 0) or 0),
                    }
            except Exception as e:
                emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        # 广度
        try:
            spot = ak.stock_zh_a_spot_em()
            if spot is not None and not spot.empty and "涨跌幅" in spot.columns:
                pct = spot["涨跌幅"]
                result["breadth"] = {
                    "total": len(spot),
                    "up": int((pct > 0).sum()),
                    "down": int((pct < 0).sum()),
                    "flat": int((pct == 0).sum()),
                    "limit_up": int((pct >= 9.5).sum()),
                    "limit_down": int((pct <= -9.5).sum()),
                    "up_ratio": round(int((pct > 0).sum()) / max(len(spot), 1) * 100, 1),
                }
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        # 板块
        try:
            for fn_name in ["stock_board_industry_name_em", "stock_board_concept_name_em"]:
                fn = getattr(ak, fn_name, None)
                if fn:
                    df = fn()
                    if df is not None and not df.empty:
                        sc = "涨跌幅" if "涨跌幅" in df.columns else df.columns[-1]
                        top = df.nlargest(10, sc)
                        result["sectors"] = [
                            {_SECTOR_FIELD_MAP.get(k, k): v for k, v in row.items()}
                            for _, row in top.iterrows()
                        ]
                        break
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return result if result["indices"] else None

    def _ak_north_flow(self, ak) -> dict:
        for fn_name in ["stock_hsgt_north_net_flow_in_em", "stock_em_hsgt_north_net_flow_in"]:
            try:
                fn = getattr(ak, fn_name, None)
                if fn:
                    df = fn(symbol="北上")
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        return {
                            "date": str(latest.get("date", "")),
                            "net_buy_amount": float(latest.get("value", 0) or 0),
                        }
            except Exception as e:
                emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
                continue
        return None

    def _ak_spot(self, ak):
        if not _API_LOCK.acquire():
            return None
        try:
            return ak.stock_zh_a_spot_em()
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None
        finally:
            _API_LOCK.release()

    def _ak_kline(self, ak, code: str, days: int):
        try:
            symbol = code
            if code.isdigit():
                symbol = f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            return df.tail(days) if df is not None and not df.empty else None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _ak_basic(self, ak, code: str) -> dict:
        try:
            info = ak.stock_individual_info_em(symbol=code)
            if info is not None:
                result = {}
                for _, row in info.iterrows():
                    result[str(row["item"])] = row["value"]
                return result
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return _NOT_SUPPORTED

    # ═══════════════════════════════════════════
    #  Source 2: 腾讯财经
    # ═══════════════════════════════════════════

    def _source_tencent(self, method: str, *args):
        if method == "fetch_indices":
            return self._tx_indices()
        if method in ("fetch_stock_spot", "fetch_full_spot"):
            # Tencent 批量行情接口(sh_a,sz_a)已失效,跳过让下游 Sina 接管
            return _NOT_SUPPORTED
        if method == "fetch_kline":
            return self._tx_kline(*args)
        if method == "fetch_basic":
            return self._tx_basic(*args)
        return _NOT_SUPPORTED

    def _tx_indices(self) -> dict:
        """腾讯财经指数数据"""
        try:
            code_map = {
                "000001": "上证指数",
                "399001": "深证成指",
                "399006": "创业板指",
                "000905": "中证500",
            }
            tx_codes = ["sh000001", "sz399001", "sz399006", "sh000905"]
            url = f"http://qt.gtimg.cn/q={','.join(tx_codes)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
            resp = _urlopen(req, timeout=10)
            text = resp.read().decode("gbk", errors="replace")
            result = {
                "indices": {},
                "breadth": {
                    "total": 0,
                    "up": 0,
                    "down": 0,
                    "flat": 0,
                    "limit_up": 0,
                    "limit_down": 0,
                    "up_ratio": 0,
                },
                "sectors": [],
                "data_time": time.strftime("%Y-%m-%d %H:%M"),
            }
            for line in text.strip().split("\n"):
                if "~" not in line:
                    continue
                parts = line.split('"')[1] if '"' in line else ""
                if not parts:
                    continue
                fields = parts.split("~")
                if len(fields) < 40:
                    continue
                idx_code = fields[2]
                idx_name = code_map.get(idx_code, idx_code)
                result["indices"][idx_name] = {
                    "price": float(fields[3] or 0),
                    "change_pct": round(float(fields[32] or 0), 2),
                    "amount": float(fields[37] or 0),
                }
            return result if result["indices"] else None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _tx_spot(self):
        """腾讯财经全市场快照 — 通过 qt.gtimg.cn 批量获取"""
        try:
            import pandas as pd

            rows = []
            # Tencent API 不支持 offset/limit 分页,一次拉取全部
            url = "http://qt.gtimg.cn/q=sh_a,sz_a"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
            resp = _urlopen(req, timeout=10)
            text = resp.read().decode("gbk", errors="replace")
            for line in text.strip().split("\n"):
                if "=" not in line:
                    continue
                parts = line.split("=")[1].strip('"').strip(";").split("~")
                if len(parts) < 45:
                    continue
                rows.append(
                    {
                        "代码": parts[2],
                        "名称": parts[1],
                        "最新价": float(parts[3] or 0),
                        "涨跌幅": float(parts[32] or 0),
                        "涨跌额": float(parts[31] or 0),
                        "成交量": float(parts[6] or 0),
                        "成交额": float(parts[37] or 0),
                        "换手率": float(parts[38] or 0),
                        "市盈率-动态": float(parts[39] or 0),
                    }
                )
            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _tx_kline(self, code: str, days: int = 90):
        """腾讯财经个股K线"""
        try:
            import pandas as pd

            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
            resp = _urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            klines = data.get("data", {}).get(f"{prefix}{code}", {}).get("day", []) or data.get(
                "data", {}
            ).get(f"{prefix}{code}", {}).get("qfqday", [])
            if not klines:
                return None
            # Handle variable column counts (some have 7 with dividend info)
            trimmed = [k[:6] for k in klines]
            df = pd.DataFrame(trimmed, columns=["date", "open", "close", "high", "low", "volume"])
            for col in ["open", "close", "high", "low", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.tail(days)
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    # ═══════════════════════════════════════════
    #  Source 3: 新浪财经
    # ═══════════════════════════════════════════

    def _tx_basic(self, code: str) -> dict:
        """腾讯财经单股基本面 — 快速获取PE/PB/市值等"""
        try:
            tx_code = "sh" + code if code.startswith(("6", "5", "9")) else "sz" + code
            url = f"http://qt.gtimg.cn/q={tx_code}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
            resp = _urlopen(req, timeout=10)
            text = resp.read().decode("gbk", errors="replace")
            fields = text.split("~")
            if len(fields) < 50:
                return None

            def _f(idx):
                try:
                    return float(fields[idx]) if fields[idx].strip() else 0
                except (ValueError, IndexError):
                    return 0

            return {
                "stock_code": fields[2],
                "stock_name": fields[1],
                "latest_price": _f(3),
                "change_pct": _f(32),
                "pe_ratio": _f(39),
                "pb_ratio": _f(46),
                "total_market_cap": _f(44) * 10000,  # 亿 -> 万
                "turnover_rate": _f(38),
                "volume": _f(6),
                "amount": _f(37) * 10000,  # 万 -> 元
            }
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _source_sina(self, method: str, *args):
        if method == "fetch_indices":
            return self._sina_indices()
        if method in ("fetch_stock_spot", "fetch_full_spot"):
            return self._sina_spot()
        if method == "fetch_kline":
            return self._sina_kline(*args)
        if method == "fetch_basic":
            return None  # Sina has no individual stock basic API
        return _NOT_SUPPORTED

    def _sina_indices(self) -> dict:
        """新浪财经指数数据"""
        try:
            code_map = {
                "s_sh000001": "上证指数",
                "s_sz399001": "深证成指",
                "s_sz399006": "创业板指",
                "s_sh000905": "中证500",
            }
            url = f"http://hq.sinajs.cn/list={','.join(code_map.keys())}"
            req = urllib.request.Request(  # noqa: S310
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
            )
            resp = _urlopen(req, timeout=10)
            text = resp.read().decode("gbk", errors="replace")
            result = {
                "indices": {},
                "breadth": {
                    "total": 0,
                    "up": 0,
                    "down": 0,
                    "flat": 0,
                    "limit_up": 0,
                    "limit_down": 0,
                    "up_ratio": 0,
                },
                "sectors": [],
                "data_time": time.strftime("%Y-%m-%d %H:%M"),
            }
            for line in text.strip().split("\n"):
                if "=" not in line:
                    continue
                # Sample: var hq_str_s_sh000001="上证指数,4162.27,-17.82,-0.43,4537630,85565199";
                before_eq = line.split("=")[0]
                code_key = before_eq.replace("var hq_str_", "").strip()
                vals_raw = line.split('"')[1] if '"' in line else ""
                vals = vals_raw.split(",")
                if len(vals) < 4:
                    continue
                name = code_map.get(code_key, code_key)
                result["indices"][name] = {
                    "price": float(vals[1] or 0),
                    "change_pct": round(float(vals[3] or 0), 2),
                    "amount": float(vals[4] or 0) if len(vals) > 4 else 0,
                }
            return result if result["indices"] else None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _sina_spot(self):
        """新浪财经全市场快照"""
        try:
            import pandas as pd

            rows = []
            for page in range(1, 6):
                url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num=800&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=auto"
                req = urllib.request.Request(  # noqa: S310
                    url,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
                )
                resp = _urlopen(req, timeout=8)
                text = resp.read().decode("gbk", errors="replace")
                batch = json.loads(text)
                if not batch:
                    break
                for item in batch:
                    code_raw = str(item.get("symbol", ""))
                    pure_code = (
                        code_raw[2:]
                        if len(code_raw) > 2 and code_raw[:2] in ("sh", "sz", "bj")
                        else code_raw
                    )
                    rows.append(
                        {
                            _SECTOR_FIELD_MAP.get(k, k): v
                            for k, v in {
                                "代码": pure_code,
                                "名称": str(item.get("name", "")),
                                "最新价": float(item.get("trade", 0) or 0),
                                "涨跌幅": float(item.get("changepercent", 0) or 0),
                                "涨跌额": float(item.get("pricechange", 0) or 0),
                                "成交量": float(item.get("volume", 0) or 0) / 100,
                                "成交额": float(item.get("amount", 0) or 0),
                                "市盈率-动态": float(item.get("per", 0) or 0),
                            }.items()
                        }
                    )
            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _sina_kline(self, code: str, days: int = 90):
        """新浪财经个股K线"""
        try:
            import pandas as pd

            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen={days}"
            req = urllib.request.Request(  # noqa: S310
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
            )
            resp = _urlopen(req, timeout=8)
            data = json.loads(resp.read().decode("utf-8"))
            if not data:
                return None
            df = pd.DataFrame(data)
            for col in ["open", "close", "high", "low", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.tail(days)
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return _NOT_SUPPORTED

    # ═══════════════════════════════════════════
    #  Source 4: Baostock (免费、稳定、无频率限制)
    # ═══════════════════════════════════════════

    def _source_baostock(self, method: str, *args):  # noqa: PLR0911
        """Baostock数据源 — 适合历史K线和基本面,无需API Key"""
        try:
            import baostock as bs
        except ImportError:
            return _NOT_SUPPORTED

        # Baostock需要login/logout,但每次login会重置连接
        # 用类级别缓存lg实例避免频繁login
        lg = self._bs_login(bs)
        if lg is None:
            return _NOT_SUPPORTED

        try:
            if method == "fetch_kline":
                return self._bs_kline(bs, *args)
            if method == "fetch_basic":
                return self._bs_basic(bs, *args)
            if method == "fetch_indices":
                return self._bs_indices(bs)
            if method == "fetch_stock_spot":
                return self._bs_spot(bs)
            return _NOT_SUPPORTED
        finally:
            pass  # 不logout,保持连接复用

    _bs_lg = None  # Module-level cache: prevent socket leak on repeated login attempts

    def _bs_login(self, bs):
        """Baostock登录 — 模块级缓存, 所有实例共享, 只尝试一次"""
        if MarketDataProvider._bs_lg is None:
            try:
                MarketDataProvider._bs_lg = bs.login()
                if MarketDataProvider._bs_lg.error_code != "0":
                    MarketDataProvider._bs_lg = False  # False = tried and failed
            except Exception:
                MarketDataProvider._bs_lg = False
        if MarketDataProvider._bs_lg is False:
            return None
        return MarketDataProvider._bs_lg

    def _bs_prepare_code(self, code: str) -> str:
        """标准化股票代码为 baostock 格式 (sh.600519 / sz.000001)"""
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith(("6", "9")):
            return f"sh.{code}"
        if code.startswith(("0", "3", "2")):
            return f"sz.{code}"
        if code.startswith(("4", "8")):
            return f"bj.{code}"
        return f"sz.{code}"  # 默认深交所

    def _bs_kline(self, bs, code: str, days: int = 90):
        """Baostock 日K线获取"""
        try:
            import pandas as pd

            bs_code = self._bs_prepare_code(code)
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

            fields = "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ"
            rs = bs.query_history_k_data_plus(
                bs_code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",  # 前复权
            )

            if rs.error_code != "0":
                return None

            rows = []
            while rs.next():
                rows.append(rs.get_row_data())

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=fields.split(","))
            for col in ["open", "high", "low", "close", "volume", "amount", "turn"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df[df["volume"] > 0]  # 过滤停牌日
            return df.tail(days)
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _bs_basic(self, bs, code: str) -> dict:
        """Baostock 个股基本面(股票基本信息 + 估值指标)"""
        try:
            bs_code = self._bs_prepare_code(code)

            # 1. 股票基本信息
            rs_basic = bs.query_stock_basic(code=bs_code)
            if rs_basic.error_code != "0":
                return None

            basic_data = {}
            while rs_basic.next():
                row = rs_basic.get_row_data()
                basic_data = {
                    "stock_code": code,
                    "stock_name": row[1] if len(row) > 1 else "",
                    "ipo_date": row[2] if len(row) > 2 else "",
                }

            # 2. 估值指标(最新一季)
            today = datetime.now().strftime("%Y-%m-%d")
            rs_val = bs.query_history_k_data_plus(
                bs_code,
                "date,peTTM,pbMRQ,psTTM",
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                end_date=today,
                frequency="d",
                adjustflag="2",
            )

            if rs_val.error_code == "0":
                rows_val = []
                while rs_val.next():
                    rows_val.append(rs_val.get_row_data())
                if rows_val:
                    latest = rows_val[-1]
                    basic_data.update(
                        {
                            "latest_price": 0,  # baostock 不提供实时价
                            "pe_ratio": float(latest[1]) if latest[1] else 0,
                            "pb_ratio": float(latest[2]) if latest[2] else 0,
                        }
                    )

            # 3. 所属行业
            rs_ind = bs.query_stock_industry(bs_code)
            if rs_ind.error_code == "0":
                while rs_ind.next():
                    row = rs_ind.get_row_data()
                    basic_data["industry"] = row[3] if len(row) > 3 else ""

            return basic_data
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _bs_indices(self, bs) -> dict:
        """Baostock 指数数据 — 仅作降级补充,覆盖率不如HTTP源"""
        try:
            result = {
                "indices": {},
                "breadth": {
                    "total": 0,
                    "up": 0,
                    "down": 0,
                    "flat": 0,
                    "limit_up": 0,
                    "limit_down": 0,
                    "up_ratio": 0,
                },
                "sectors": [],
                "data_time": time.strftime("%Y-%m-%d %H:%M"),
            }

            # Baostock 支持的指数
            index_map = {
                "sh.000001": "上证指数",
                "sz.399001": "深证成指",
                "sz.399006": "创业板指",
                "sh.000905": "中证500",
            }

            today = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            fields = "date,code,close,pctChg,amount"

            for bs_idx_code, name in index_map.items():
                try:
                    rs = bs.query_history_k_data_plus(
                        bs_idx_code,
                        fields,
                        start_date=start,
                        end_date=today,
                        frequency="d",
                        adjustflag="1",
                    )
                    if rs.error_code == "0":
                        rows = []
                        while rs.next():
                            rows.append(rs.get_row_data())
                        if rows:
                            latest = rows[-1]
                            result["indices"][name] = {
                                "price": float(latest[2]) if latest[2] else 0,
                                "change_pct": round(float(latest[3]) or 0, 2),
                                "amount": float(latest[4]) if len(latest) > 4 and latest[4] else 0,
                            }
                except Exception as e:
                    emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
                    continue

            return result if result["indices"] else None
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _bs_spot(self, bs):
        """Baostock 不支持实时行情,返回None由其他源处理"""
        return _NOT_SUPPORTED

    # ═══════════════════════════════════════════
    #  Source 5: efinance
    # ═══════════════════════════════════════════

    def _source_efinance(self, method: str, *args):  # noqa: PLR0911
        # Use urllib (system proxy handles HTTPS correctly for domestic sites)
        if method == "fetch_stock_spot":
            try:
                import json as _json

                import pandas as pd

                _EM_FIELDS = "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152"
                _EM_COLUMNS = {
                    "f12": "代码",
                    "f14": "名称",
                    "f2": "最新价",
                    "f3": "涨跌幅",
                    "f4": "涨跌额",
                    "f5": "成交量",
                    "f6": "成交额",
                    "f7": "振幅",
                    "f8": "换手率",
                    "f9": "市盈率-动态",
                    "f10": "量比",
                    "f15": "最高",
                    "f16": "最低",
                    "f17": "今开",
                    "f18": "昨收",
                    "f20": "总市值",
                    "f21": "流通市值",
                }
                all_rows = []
                for pn in range(1, 6):
                    url = (
                        f"https://push2.eastmoney.com/api/qt/clist/get?"
                        f"pn={pn}&pz=1500&po=1&np=1&fltt=2&invt=2&fid=f12"
                        f"&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
                        f"&fields={_EM_FIELDS}"
                    )
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
                    resp = _urlopen(req, timeout=8)
                    data = _json.loads(resp.read().decode("utf-8"))
                    diff = data.get("data", {}).get("diff", [])
                    if not diff:
                        break
                    all_rows.extend(diff)
                if not all_rows:
                    return None
                df = pd.DataFrame(all_rows)
                df = df.rename(columns=_EM_COLUMNS)
                for col in _EM_COLUMNS.values():
                    if col not in df.columns:
                        df[col] = 0
                return df
            except Exception as e:
                emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
                return None
        try:
            import efinance as ef
        except ImportError:
            return _NOT_SUPPORTED
        if method == "fetch_kline":
            try:
                df = ef.stock.get_quote_history(args[0], klt=101)
                return df.tail(args[1]) if df is not None and not df.empty and len(args) > 1 else df
            except Exception as e:
                emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
                return None
        elif method == "fetch_basic":
            try:
                info = ef.stock.get_base_info(args[0])
                return info if isinstance(info, dict) else {}
            except Exception as e:
                emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
                return None
        return _NOT_SUPPORTED

    def _source_eastmoney(self, method: str, *args):
        if method == "fetch_hot_stocks_em":
            return self._em_hot_stocks(*args)
        if method == "fetch_full_spot":
            return None  # 委托给akshare
        if method == "fetch_kline":
            return self._em_kline(*args)
        return _NOT_SUPPORTED

    def _em_kline(self, code: str, days: int = 90):
        """EastMoney kline via urllib (auto-routes through proxy if available)"""
        try:
            import json as _json
            from datetime import datetime, timedelta

            import pandas as pd

            secid = "1." + code if code.startswith(("6", "5", "9")) else "0." + code

            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

            url = (
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
                f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                f"&klt=101&fqt=1&beg={start_date}&end={end_date}"
            )
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            )
            resp = _urlopen(req, timeout=15)
            data = _json.loads(resp.read().decode("utf-8"))
            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return None

            rows = []
            for k in klines:
                parts = k.split(",")
                if len(parts) >= 6:
                    rows.append(
                        {
                            "date": parts[0],
                            "open": float(parts[1]),
                            "close": float(parts[2]),
                            "high": float(parts[3]),
                            "low": float(parts[4]),
                            "volume": float(parts[5]),
                            "amount": float(parts[6]) if len(parts) > 6 else 0,
                            "change_pct": float(parts[8]) if len(parts) > 8 else 0,
                        }
                    )

            if rows:
                df = pd.DataFrame(rows)
                return df.tail(days)
        except Exception as e:
            logger.debug("[MarketData] EastMoney kline failed for %s: %s", code, str(e)[:80])
        return None

    def _em_hot_stocks(self, limit: int = 100) -> list:
        """EastMoney热榜 — 返回股票代码列表"""
        try:
            import json
            import urllib.request

            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3"
                "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12"
            )
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            )
            resp = _urlopen(req, timeout=8)
            data = json.loads(resp.read().decode("utf-8"))
            return [i.get("f12", "") for i in data.get("data", {}).get("diff", []) if i.get("f12")]
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
            return None

    def _source_eastmoney_hot(self, sort: str = "change_pct", limit: int = 100) -> list:
        """东方财富全市场行情 — 免费、快速、可靠"""
        try:
            fid_map = {"change_pct": "f3", "volume": "f5", "turnover": "f6"}
            fid = fid_map.get(sort, "f3")
            url = (
                f"https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid={fid}"
                f"&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
                f"&fields=f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
            )
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            resp = _urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", {}).get("diff", [])
            if not items:
                return None
            result = []
            for item in items:
                result.append(
                    {
                        "stock_code": str(item.get("f12", "")),
                        "stock_name": str(item.get("f14", "")),
                        "price": float(item.get("f2", 0) or 0),
                        "change_pct": float(item.get("f3", 0) or 0),
                        "change_amt": float(item.get("f4", 0) or 0),
                        "volume": float(item.get("f5", 0) or 0),
                        "amount": float(item.get("f6", 0) or 0),
                        "turnover_rate": float(item.get("f8", 0) or 0),
                        "pe_ratio": float(item.get("f9", 0) or 0),
                    }
                )
            return result
        except Exception as e:
            logger.warning("[MarketData] EastMoney failed: %s", e)
            return _NOT_SUPPORTED

    def fetch_industry_batch(self, max_pages: int = 60) -> dict:
        """Fetch industry data for all A-share stocks from EastMoney.
        Returns {stock_code: industry_name} mapping.
        Uses domestic connection (bypasses proxy) to avoid SOCKS5 issues."""
        import time as _time

        try:
            import requests as _req
        except ImportError:
            emit_log("WARNING", "data_init", "requests not installed, cannot fetch industry data")
            return {}

        # Use NO_PROXY/domestic opener to avoid SOCKS5 issues
        session = _req.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://quote.eastmoney.com/",
            }
        )
        # Explicitly clear all proxy settings for this session
        session.trust_env = False
        session.proxies = {"http": "", "https": ""}

        url = "https://push2.eastmoney.com/api/qt/clist/get"
        result = {}
        total_pages = 0

        for pn in range(1, max_pages + 1):
            params = {
                "pn": str(pn),
                "pz": "100",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f12",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f12,f14,f100",
            }
            try:
                resp = session.get(url, params=params, timeout=15)
                data = resp.json()
                items = data.get("data", {}).get("diff", [])
                total_pages += 1
                for item in items:
                    code = item.get("f12", "")
                    industry = item.get("f100", "")
                    if code and industry:
                        result[code] = industry
                if len(items) < 100:
                    break
            except Exception as e:
                emit_log("WARNING", "market_data", f"Industry page {pn} failed: {str(e)[:80]}")
                if pn <= 3:
                    _time.sleep(2)
                else:
                    break
            _time.sleep(0.5)

        logger.info(
            "[MarketData] Industry batch: fetched %d entries from %d pages",
            len(result),
            total_pages,
        )
        return result

    # ═══════════════════════════════════════════
    #  Source 6: TickFlow
    # ═══════════════════════════════════════════

    def _source_tickflow(self, method: str, *args):
        if method == "fetch_kline":
            return self._tf_kline(*args)
        if method == "fetch_stock_spot":
            return self._tf_spot()
        if method == "fetch_basic":
            return self._tf_basic(*args)
        return _NOT_SUPPORTED

    def _tf_kline(self, code: str, days: int = 90):
        """TickFlow 个股K线"""
        try:
            url = f"{_TICKFLOW_BASE}/stock/kline?code={code}&period=daily&count={days}"
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={"Authorization": f"Bearer {_TICKFLOW_TOKEN}", "User-Agent": "Mozilla/5.0"},
            )
            resp = _urlopen(req, timeout=8)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == 0 and "data" in data:
                import pandas as pd

                df = pd.DataFrame(data["data"])
                for col in ["open", "close", "high", "low", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                return df.tail(days)
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return None

    def _tf_spot(self):
        """TickFlow 全市场快照"""
        try:
            url = f"{_TICKFLOW_BASE}/market/spot?market=cn"
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={"Authorization": f"Bearer {_TICKFLOW_TOKEN}", "User-Agent": "Mozilla/5.0"},
            )
            resp = _urlopen(req, timeout=8)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == 0 and "data" in data:
                import pandas as pd

                return pd.DataFrame(data["data"])
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return None

    def _tf_basic(self, code: str):
        """TickFlow 个股基本面"""
        try:
            url = f"{_TICKFLOW_BASE}/stock/info?code={code}"
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={"Authorization": f"Bearer {_TICKFLOW_TOKEN}", "User-Agent": "Mozilla/5.0"},
            )
            resp = _urlopen(req, timeout=8)
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == 0 and "data" in data:
                return data["data"]
        except Exception as e:
            emit_log("WARNING", "market_data", f"Data fetch failed: {str(e)[:100]}")
        return None

    # ═══════════════════════════════════════════
    #  Source 7: Yahoo Finance — 代理自动切换, 全球数据
    # ═══════════════════════════════════════════

    def _source_yfinance(self, method: str, *args):
        """Yahoo Finance 数据源 — 通过 Hiddify 代理获取 A 股数据"""
        try:
            from providers.sources.yfinance_src import YFinanceAdapter

            adapter = YFinanceAdapter()
            if method == "fetch_basic":
                return adapter.fetch_basic(*args)
            if method == "fetch_kline":
                return adapter.fetch_kline(*args)
        except ImportError:
            return None  # yfinance not installed — skip silently
        except Exception as e:
            err = str(e)[:80]
            emit_log("WARNING", "market_data", f"yfinance {method} failed: {err}")
            return None
        return None

    # ═══════════════════════════════════════════
    #  Source 8: ZZShare — 日频数据 (股票名/行业/K线/热度)
    # ═══════════════════════════════════════════

    def _source_zzshare(self, method: str, *args):
        """ZZShare 数据源 — 日频数据: stock_basic / kline / hot_stocks (仅日频)"""
        try:
            from providers.sources.zzshare_src import ZZShareAdapter

            adapter = ZZShareAdapter()
            if method == "fetch_basic":
                return adapter.fetch_basic(*args)
            if method == "fetch_kline":
                return adapter.fetch_kline(*args)
            if method == "fetch_hot_stocks":
                return adapter.fetch_hot_stocks(*args)
        except ImportError:
            return None  # zzshare not installed — skip silently
        except Exception as e:
            err = str(e)[:80]
            emit_log("WARNING", "market_data", f"zzshare {method} failed: {err}")
            return None
        return None

    def _zz_test_connect(self):
        """ZZShare 连接测试 — 直接 ping API 根路径"""
        try:
            import urllib.request

            req = urllib.request.Request("https://api.zizizaizai.com/")
            resp = _urlopen(req, timeout=5)
            return resp.status == 200
        except Exception as e:
            emit_log("DEBUG", "market_data", f"zzshare test: {str(e)[:60]}")
            return None

    # ═══════════════════════════════════════════
    #  Source 9: Tushare (免费版 — 基本面/K线/指数)
    # ═══════════════════════════════════════════

    def _get_tushare_adapter(self):
        global _tushare_adapter  # noqa: PLW0603
        if _tushare_adapter is None:
            from providers.sources.tushare import TushareAdapter

            _tushare_adapter = TushareAdapter()
        return _tushare_adapter

    def _source_tushare(self, method: str, *args):
        adapter = self._get_tushare_adapter()
        if method == "fetch_indices":
            return adapter.fetch_indices()
        if method == "fetch_kline":
            return adapter.fetch_kline(*args)
        if method == "fetch_basic":
            return adapter.fetch_basic(*args)
        return _NOT_SUPPORTED
