"""Tushare 数据源适配器 (免费基础版)

免费版接口频率限制:
- stock_basic: 5次/分钟
- daily: 200次/分钟
- 指数类(index_daily等): 200次/分钟
"""

import contextlib
import logging
import os
import time

import pandas as pd
import tushare as ts

from providers.source_base import (
    PermanentError,
    RateLimitError,
    SourceAdapter,
    TransientError,
    classify_error,
)
from shared.logging import emit_log

logger = logging.getLogger(__name__)

_TOKEN = ""
_TOKEN_CONFIGURED = False
_pro = None


def _resolve_token() -> str:
    # 确保 .env 已加载 (在 server.py/launch.py 可能未提前加载)
    _dotenv_loaded = getattr(_resolve_token, "_loaded", False)
    if not _dotenv_loaded:
        try:
            _env_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", ".env"
            )
            if os.path.exists(_env_path):
                with open(_env_path, encoding="utf-8") as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line and not _line.startswith("#") and "=" in _line:
                            _k, _v = _line.split("=", 1)
                            _v = _v.strip().strip('"').strip("'")
                            if _k.strip() == "TUSHARE_TOKEN":
                                os.environ.setdefault("TUSHARE_TOKEN", _v)
            _resolve_token._loaded = True  # type: ignore[attr-defined]
        except Exception:
            pass

    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token:
        return token
    try:
        from shared.config import Config

        cfg_token = Config().get("llm_providers.tushare.api_key", "")
        if isinstance(cfg_token, str) and cfg_token.strip():
            return cfg_token.strip()
    except Exception:
        pass
    return ""


def _ensure_token_configured() -> None:
    global _TOKEN, _TOKEN_CONFIGURED, _pro  # noqa: PLW0603
    if _TOKEN_CONFIGURED:
        return
    _TOKEN = _resolve_token()
    with contextlib.suppress(Exception):
        if _TOKEN:
            ts.set_token(_TOKEN)
    _pro = None
    _TOKEN_CONFIGURED = True


def _get_pro():
    _ensure_token_configured()
    global _pro  # noqa: PLW0603
    if _pro is None:
        if not _TOKEN:
            raise RuntimeError("Tushare token not configured")
        _pro = ts.pro_api(_TOKEN)
    return _pro


class _SimpleRateLimiter:
    """简单频率限制器 — 滑动窗口, 按分钟计数"""

    def __init__(self, max_per_minute: int):
        self._max = max_per_minute
        self._timestamps: list[float] = []

    def check(self):
        """检查是否超限, 超限则抛出 RateLimitError"""
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        if len(self._timestamps) >= self._max:
            wait = 60 - (now - self._timestamps[0])
            raise RateLimitError(
                f"Tushare 频率限制: {self._max}次/分钟, 需等待{wait:.0f}s", "tushare"
            )
        self._timestamps.append(now)


# 免费版各接口频率限制 (实测: stock_basic=1次/分, daily=200次/分)
_stock_basic_limiter = _SimpleRateLimiter(max_per_minute=1)  # 实际限1次/分钟
_daily_limiter = _SimpleRateLimiter(max_per_minute=100)  # 限200,留余量
_index_daily_limiter = _SimpleRateLimiter(max_per_minute=1)  # 限1次/分钟
_fina_limiter = _SimpleRateLimiter(max_per_minute=1)  # fina_indicator = 1次/分钟


class TushareAdapter(SourceAdapter):
    name = "tushare"
    priority = 22  # 在 Tencent(17) 之后, Sina(25) 之前
    timeout = 8.0

    # ── 批量行情快照 (daily_basic: PE/PB/换手率/市值/股息) ──

    def fetch_daily_basic(self, trade_date: str) -> "pd.DataFrame | None":
        """获取全市场批量行情快照 (一次调用覆盖 ~5500只股票)

        返回字段: ts_code, pe, pb, turnover_rate, dv_ratio, total_mv, circ_mv
        """
        try:
            _daily_limiter.check()
            pro = _get_pro()
            return pro.daily_basic(trade_date=trade_date)
        except RateLimitError:
            raise
        except (RuntimeError, Exception) as e:
            msg = str(e)
            if "token" in msg:
                raise PermanentError(f"Tushare token error: {msg}", "tushare")  # noqa: B904
            if "频率" in msg or "超过" in msg:
                raise RateLimitError(f"Tushare daily_basic rate limit: {msg}", "tushare")  # noqa: B904
            raise TransientError(f"Tushare daily_basic: {msg}", "tushare")  # noqa: B904

    # ── 指数 (使用大盘指数日线) ──

    def fetch_indices(self) -> dict | None:
        try:
            pro = _get_pro()
            # index_daily 是指数专用接口, daily 不返回指数数据
            index_map = {
                "000001.SH": "上证指数",
                "399001.SZ": "深证成指",
                "399006.SZ": "创业板指",
                "000905.SH": "中证500",
            }
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
            for ts_code, name in index_map.items():
                try:
                    _index_daily_limiter.check()
                    df = pro.index_daily(ts_code=ts_code, start_date="", end_date="")
                    if df is not None and not df.empty:
                        latest = df.iloc[0]
                        prev = df.iloc[1] if len(df) > 1 else latest
                        prev_close = float(prev.get("close", prev.get("pre_close", 0)))
                        close = float(latest.get("close", 0))
                        change_pct = (
                            round((close - prev_close) / prev_close * 100, 2) if prev_close else 0
                        )
                        result["indices"][name] = {
                            "price": close,
                            "change_pct": change_pct,
                            "amount": float(latest.get("amount", 0) or 0),
                        }
                except RateLimitError:
                    raise
                except Exception as exc:
                    logger.debug("index %s fetch failed: %s", name, exc)
                    continue
            return result if result["indices"] else None
        except RateLimitError:
            raise
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── K线 ──

    def fetch_kline(self, code: str, days: int = 90):
        try:
            _daily_limiter.check()
            pro = _get_pro()
            suffix = ".SH" if code.startswith(("6", "9")) else ".SZ"
            df = pro.daily(ts_code=code + suffix, start_date="", end_date="")
            if df is None or df.empty:
                return None
            df = df.sort_values("trade_date")
            df.rename(
                columns={
                    "trade_date": "date",
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "vol": "volume",
                    "amount": "amount",
                    "pct_chg": "change_pct",
                },
                inplace=True,
            )
            for col in ["open", "high", "low", "close", "volume", "amount"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.tail(days)
        except RateLimitError:
            raise
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 基本面 ──

    def fetch_basic(self, code: str) -> dict | None:
        try:
            pro = _get_pro()
            suffix = ".SH" if code.startswith(("6", "9")) else ".SZ"
            ts_code = code + suffix

            # stock_basic: 频率限制 5次/分钟
            _stock_basic_limiter.check()
            info = pro.stock_basic(ts_code=ts_code)
            if info is None or info.empty:
                return None
            row = info.iloc[0]
            result = {
                "stock_code": code,
                "stock_name": str(row.get("name", "")),
                "industry": str(row.get("industry", "")),
                "market": str(row.get("market", "")),
            }

            # daily 接口获取最新价
            _daily_limiter.check()
            daily = pro.daily(ts_code=ts_code, start_date="", end_date="")
            if daily is not None and not daily.empty:
                latest = daily.iloc[0]
                result["latest_price"] = float(latest.get("close", 0))
                result["change_pct"] = float(latest.get("pct_chg", 0) or 0)
                result["volume"] = float(latest.get("vol", 0) or 0)
                result["amount"] = float(latest.get("amount", 0) or 0)

            # daily_basic: PE, PB, turnover_rate, total_market_cap (同200次/分钟池)
            try:
                _daily_limiter.check()
                basic = pro.daily_basic(ts_code=ts_code, start_date="", end_date="")
                if basic is not None and not basic.empty:
                    b = basic.iloc[0]
                    if result.get("pe_ratio") is None or result.get("pe_ratio", 0) == 0:
                        result["pe_ratio"] = float(b.get("pe", 0) or 0)
                    result["pb_ratio"] = float(b.get("pb", 0) or 0)
                    result["turnover_rate"] = float(b.get("turnover_rate", 0) or 0)
                    mcap = float(b.get("total_mv", 0) or 0)
                    if mcap > 0:
                        result["total_market_cap"] = round(mcap / 10000, 2)
            except Exception:
                pass

            # fina_indicator: ROE, EPS, bvps, gross_margin (1次/分钟)
            try:
                _fina_limiter.check()
                fina = pro.fina_indicator(ts_code=ts_code, start_date="", end_date="")
                if fina is not None and not fina.empty:
                    f = fina.iloc[0]
                    result["roe"] = float(f.get("roe", 0) or 0)
                    result["eps"] = float(f.get("eps", 0) or 0)
                    result["bvps"] = float(f.get("bps", 0) or 0)
                    result["gross_margin"] = (
                        float(f.get("gross_margin", 0) or 0) if "gross_margin" in f.index else 0
                    )
                    result["debt_to_equity"] = float(f.get("debt_to_equity", 0) or 0)
                    result["free_cash_flow"] = float(f.get("free_cash_flow", 0) or 0)
                    result["net_income"] = float(f.get("net_profit_is", 0) or 0)
            except Exception:
                pass

            return result
        except RateLimitError:
            raise
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            _ensure_token_configured()
            if not _TOKEN:
                return False
            _daily_limiter.check()
            pro = _get_pro()
            df = pro.daily(ts_code="000001.SH", start_date="", end_date="")
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "tushare", f"Operation failed: {str(e)[:100]}")
            return False
