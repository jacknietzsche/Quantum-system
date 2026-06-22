"""Yahoo Finance 适配器 — 支持 Hiddify 代理自动切换

Yahoo Finance 对 A 股使用:
  - 600519.SS (上海)
  - 000001.SZ (深圳)

如果 Hiddify 代理(http://127.0.0.1:12334) 在线则自动走代理,
否则直连 (直连在中国网络可能被限流, 降级到 tencent/sina/tushare)。

代理检测:
  - 每次请求前探测: socket 连接 127.0.0.1:12334 (超时 500ms)
  - 在线 → 临时设置 HTTP_PROXY/HTTPS_PROXY → yfinance 通过代理请求
  - 不在线 → 直连 (大概率 429 Rate Limit)
"""

import contextlib
import logging
import os
import socket as _socket
import threading
from datetime import datetime, timedelta

import pandas as pd

from providers.source_base import RateLimitError, SourceAdapter, TransientError

logger = logging.getLogger(__name__)

_PROXY_HOST = "127.0.0.1"
_PROXY_PORT = 12334
_PROXY_URL = f"http://{_PROXY_HOST}:{_PROXY_PORT}"

# ── 代理检测(缓存 30s, 线程安全) ──
_proxy_available: bool | None = None
_proxy_last_check = 0.0
_proxy_lock = threading.Lock()


def _check_proxy() -> bool:
    """检测 Hiddify 代理是否在线 (socket 连接, 500ms 超时, 线程安全)"""
    global _proxy_available, _proxy_last_check  # noqa: PLW0603
    now = datetime.now().timestamp()
    with _proxy_lock:
        if _proxy_available is not None and now - _proxy_last_check < 30:
            return _proxy_available
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((_PROXY_HOST, _PROXY_PORT))
            s.close()
            _proxy_available = True
            logger.debug(f"[yfinance] Hiddify proxy OK ({_PROXY_URL})")
        except (TimeoutError, OSError):
            _proxy_available = False
            logger.debug("[yfinance] Hiddify proxy not available, direct connection")
        _proxy_last_check = now
        return _proxy_available


@contextlib.contextmanager
def _proxy_env():
    """临时设置 HTTP_PROXY 环境变量 (若代理在线), 用完恢复"""
    use_proxy = _check_proxy()
    saved = {}
    if use_proxy:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            saved[k] = os.environ.get(k)
            os.environ[k] = _PROXY_URL
    try:
        yield
    finally:
        if use_proxy:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def _to_yahoo(code: str) -> str:
    """A股代码 → Yahoo Finance 格式"""
    c = code.strip()
    if c.startswith(("6", "9")):
        return f"{c}.SS"
    return f"{c}.SZ"


class YFinanceAdapter(SourceAdapter):
    name = "yfinance"
    priority = 20
    timeout = 15.0

    def fetch_basic(self, code: str) -> dict | None:
        try:
            import yfinance as yf

            with _proxy_env():
                yahoo_code = _to_yahoo(code)
                ticker = yf.Ticker(yahoo_code)
                info = ticker.info if hasattr(ticker, "info") else {}

            name = info.get("longName") or info.get("shortName") or ""
            if not name:
                return None

            market_cap = info.get("marketCap", 0) or 0
            return {
                "stock_name": name,
                "latest_price": float(
                    info.get("currentPrice", info.get("regularMarketPrice", 0)) or 0
                ),
                "change_pct": float(info.get("regularMarketChangePercent", 0) or 0),
                "pe_ratio": float(info.get("trailingPE", info.get("forwardPE", 0)) or 0),
                "pb_ratio": float(info.get("priceToBook", 0) or 0),
                "total_market_cap": round(market_cap / 100_000_000.0, 2) if market_cap > 1e9 else 0,
                "turnover_rate": 0,
                "high": float(info.get("dayHigh", 0) or 0),
                "low": float(info.get("dayLow", 0) or 0),
                "volume": float(info.get("volume", 0) or 0),
                "amount": 0,
                "roe": float(info.get("returnOnEquity", 0) or 0),
                "eps": float(info.get("trailingEps", 0) or 0),
                "dividend_yield": float(info.get("dividendYield", 0) or 0),
            }
        except ImportError:
            logger.warning("[yfinance] yfinance not installed")
            return None
        except Exception as e:
            err_name = type(e).__name__
            if "RateLimit" in err_name or "429" in str(e):
                raise RateLimitError(f"[yfinance] {code} 限流: {e}") from e
            raise TransientError(f"[yfinance] {code} fetch_basic failed: {e}") from e

    def fetch_kline(self, code: str, days: int = 90) -> "pd.DataFrame | None":
        try:
            import yfinance as yf

            yahoo_code = _to_yahoo(code)
            end = datetime.now()
            start = end - timedelta(days=days + 10)

            with _proxy_env():
                ticker = yf.Ticker(yahoo_code)
                df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

            if df is None or df.empty:
                return None

            df = df.reset_index()
            df = df.rename(
                columns={
                    "Date": "date",
                    "Open": "open",
                    "Close": "close",
                    "High": "high",
                    "Low": "low",
                    "Volume": "volume",
                }
            )
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            df = df.tail(days).reset_index(drop=True)
            return df[["date", "open", "close", "high", "low", "volume"]]
        except ImportError:
            logger.warning("[yfinance] yfinance not installed")
            return None
        except Exception as e:
            err_name = type(e).__name__
            if "RateLimit" in err_name or "429" in str(e):
                raise RateLimitError(f"[yfinance] {code} 限流: {e}") from e
            raise TransientError(f"[yfinance] {code} fetch_kline failed: {e}") from e

    def test_connect(self) -> bool:
        try:
            result = self.fetch_basic("600519")
            return result is not None and bool(result.get("stock_name"))
        except Exception:
            return False
