"""
合规数据源管理器 — 仅日频级别数据

数据源优先级 (按A股日频数据稳定性+全面性):
1. Tushare (免费版) — A股日K线/财务/指数,最全面稳定
2. yfinance — 港股/美股日K线,Yahoo官方接口
3. zzshare — A股日K线/实时快照,轻量级

特点:
- 仅获取日频数据 (无分钟线/逐笔)
- 遵守请求频率限制 (≤1次/秒, ≤5000次/天)
- 自动降级: 主源失败 → 次源
- 数据来源标注
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger("ashare.data")


class RateLimiter:
    """请求频率限制器 — 日频数据请求量小,限制较宽松"""

    def __init__(self, max_per_second: int = 1, max_per_day: int = 5000):
        self.max_per_second = max_per_second
        self.max_per_day = max_per_day
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._daily_count = 0
        self._daily_reset_date = datetime.now().date()

    def acquire(self) -> bool:
        """获取请求许可"""
        with self._lock:
            today = datetime.now().date()
            if today != self._daily_reset_date:
                self._daily_count = 0
                self._daily_reset_date = today
            if self._daily_count >= self.max_per_day:
                logger.warning(f"[频率限制] 已达每日上限 {self.max_per_day} 次")
                return False
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < 1.0 / self.max_per_second:
                time.sleep(1.0 / self.max_per_second - elapsed)
            self._last_request_time = time.time()
            self._daily_count += 1
            return True

    @property
    def daily_remaining(self) -> int:
        with self._lock:
            today = datetime.now().date()
            if today != self._daily_reset_date:
                return self.max_per_day
            return max(0, self.max_per_day - self._daily_count)


class DailyDataSource:
    """日频合规数据源管理器

    仅获取日频级别数据:
    - 日K线 (OHLCV)
    - 日频基本面 (财务报表)
    - 日频市场概况 (指数/涨跌家数)
    """

    def __init__(self, tushare_token: str = ""):
        self.tushare_token = tushare_token or os.environ.get("TUSHARE_TOKEN", "")
        self.limiter = RateLimiter(max_per_second=1, max_per_day=5000)
        self._tushare_pro = None
        self._cache: dict[str, Any] = {}  # 简单缓存
        self._cache_ttl = 3600  # 1小时缓存

    def _get_tushare(self):
        """懒加载 Tushare Pro"""
        if self._tushare_pro is None and self.tushare_token:
            try:
                import tushare as ts

                ts.set_token(self.tushare_token)
                self._tushare_pro = ts.pro_api()
                logger.info("[日频数据] Tushare Pro 已初始化")
            except Exception as e:
                logger.warning(f"[日频数据] Tushare 初始化失败: {e}")
        return self._tushare_pro

    # ═══════════════════════════════════════════════════
    #  日K线 (核心功能)  # noqa: ERA001
    # ═══════════════════════════════════════════════════

    def fetch_daily_kline(
        self,
        stock_code: str,
        start_date: str = "",
        end_date: str = "",
        days: int = 250,
    ) -> tuple[pd.DataFrame, str]:
        """获取日K线数据

        Args:
            stock_code: 股票代码 (如 "600519")
            start_date: 开始日期 (如 "2025-01-01"),优先级高于days
            end_date: 结束日期 (默认今天)
            days: 回溯天数 (默认250天≈1年交易日)

        Returns:
            (DataFrame[date,open,high,low,close,volume,amount], 数据来源)
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=days * 1.5)).strftime("%Y-%m-%d")

        # 尝试顺序: Tushare → yfinance → zzshare
        sources = [
            ("Tushare", self._ts_daily),
            ("yfinance", self._yf_daily),
            ("zzshare", self._zz_daily),
        ]
        for name, fn in sources:
            if not self.limiter.acquire():
                continue
            try:
                df = fn(stock_code, start_date, end_date)
                if df is not None and not df.empty:
                    logger.info(f"[日频] {name} 获取 {stock_code} 日K线 {len(df)} 条")
                    return df, name
            except Exception as e:
                logger.debug(f"[日频] {name} 失败: {e}")
                continue

        return pd.DataFrame(), "none"

    def _ts_daily(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        """Tushare 日K线"""
        pro = self._get_tushare()
        if not pro:
            return None
        ts_code = f"{code}.{'SH' if code.startswith(('6', '9')) else 'SZ'}"
        df = pro.daily(
            ts_code=ts_code, start_date=start.replace("-", ""), end_date=end.replace("-", "")
        )
        if df is not None and not df.empty:
            df = df.rename(columns={"trade_date": "date", "vol": "volume"})
            df["date"] = pd.to_datetime(df["date"])
            return df.sort_values("date")[
                ["date", "open", "high", "low", "close", "volume", "amount"]
            ].reset_index(drop=True)
        return None

    def _yf_daily(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        """yfinance 日K线"""
        try:
            import yfinance as yf
        except ImportError:
            return None

        ticker = f"{code}.{'SS' if code.startswith(('6', '9')) else 'SZ'}"
        df = yf.Ticker(ticker).history(start=start, end=end)
        if df is not None and not df.empty:
            df = df.reset_index()
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            df["amount"] = df["Volume"] * df["Close"]
            return df.rename(
                columns={
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )[["date", "open", "high", "low", "close", "volume", "amount"]]
        return None

    def _zz_daily(self, code: str, start: str, end: str) -> pd.DataFrame | None:
        """zzshare 日K线(可选依赖)"""
        try:
            import importlib.util

            if importlib.util.find_spec("zzshare") is None:
                return None
            from zzshare import get_hist_data

            df = get_hist_data(code, start=start.replace("-", ""), end=end.replace("-", ""))
            if df is not None and not df.empty:
                df = df.reset_index()
                df["date"] = pd.to_datetime(df["date"])
                return df.sort_values("date")[
                    ["date", "open", "high", "low", "close", "volume", "amount"]
                ].reset_index(drop=True)
        except Exception as e:
            logger.debug("compliant_data parse failed for %s: %s", code, e)
        return None

    # ═══════════════════════════════════════════════════
    #  日频市场概况
    # ═══════════════════════════════════════════════════

    def fetch_market_overview(self, date: str = "") -> tuple[dict[str, Any], str]:
        """获取日频市场概况 (指数/涨跌家数)

        Returns:
            (概况字典, 数据来源)
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Tushare 指数日线
        pro = self._get_tushare()
        if pro and self.limiter.acquire():
            try:
                # 上证指数
                sh = pro.index_daily(
                    ts_code="000001.SH",
                    start_date=date.replace("-", ""),
                    end_date=date.replace("-", ""),
                )
                # 深证成指
                sz = pro.index_daily(
                    ts_code="399001.SZ",
                    start_date=date.replace("-", ""),
                    end_date=date.replace("-", ""),
                )
                # 创业板指
                cy = pro.index_daily(
                    ts_code="399006.SZ",
                    start_date=date.replace("-", ""),
                    end_date=date.replace("-", ""),
                )

                result: dict = {"date": date, "indices": {}}
                for name, df in [("上证指数", sh), ("深证成指", sz), ("创业板指", cy)]:
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        result["indices"][name] = {
                            "close": float(row.get("close", 0)),
                            "change_pct": float(row.get("pct_chg", 0)),
                            "volume": float(row.get("vol", 0)),
                        }
                return result, "Tushare"
            except Exception as e:
                logger.debug(f"[日频] 市场概况失败: {e}")

        return {}, "none"

    # ═══════════════════════════════════════════════════
    #  日频财务数据
    # ═══════════════════════════════════════════════════

    def fetch_fundamentals(self, stock_code: str) -> tuple[dict[str, Any], str]:
        """获取日频基本面数据 (最新财报)

        Returns:
            (财务指标字典, 数据来源)
        """
        pro = self._get_tushare()
        if not pro or not self.limiter.acquire():
            return {}, "none"

        try:
            ts_code = f"{stock_code}.{'SH' if stock_code.startswith(('6', '9')) else 'SZ'}"

            # 最新财务指标
            df = pro.fina_indicator(ts_code=ts_code, period="")
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "code": stock_code,
                    "period": row.get("ann_date", ""),
                    "roe": float(row.get("roe", 0) or 0),
                    "roa": float(row.get("roa", 0) or 0),
                    "gross_margin": float(row.get("grossprofit_margin", 0) or 0),
                    "net_margin": float(row.get("netprofit_margin", 0) or 0),
                    "debt_to_equity": float(row.get("debt_to_eqt", 0) or 0),
                    "current_ratio": float(row.get("current_ratio", 0) or 0),
                    "revenue_growth": float(row.get("or_yoy", 0) or 0),
                    "profit_growth": float(row.get("netprofit_yoy", 0) or 0),
                }, "Tushare"
        except Exception as e:
            logger.debug(f"[日频] 基本面数据失败: {e}")

        return {}, "none"

    # ═══════════════════════════════════════════════════
    #  信息获取
    # ═══════════════════════════════════════════════════

    def get_source_info(self) -> dict[str, Any]:
        """数据源信息"""
        return {
            "sources": ["Tushare (免费版)", "yfinance", "zzshare"],
            "data_level": "日频",
            "rate_limit": {
                "max_per_second": self.limiter.max_per_second,
                "max_per_day": self.limiter.max_per_day,
                "daily_remaining": self.limiter.daily_remaining,
            },
        }


# ═══════════════════════════════════════════════════
#  全局实例
# ═══════════════════════════════════════════════════

_daily_source: DailyDataSource | None = None


def get_daily_source() -> DailyDataSource:
    global _daily_source  # noqa: PLW0603
    if _daily_source is None:
        _daily_source = DailyDataSource()
    return _daily_source
