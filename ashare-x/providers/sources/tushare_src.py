"""Tushare 数据源适配器（免费版）。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import cast

from core.config import Config
from providers.base import SourceAdapter
from providers.normalizer import StockCodeNormalizer

logger = logging.getLogger("ashare-x.providers.tushare")


class TushareAdapter(SourceAdapter):
    """Tushare 免费版适配器。

    symbol 格式为 ``600519.SH`` / ``000001.SZ``。
    支持 K 线、基础信息、全市场股票列表。
    """

    def __init__(self):
        super().__init__(name="tushare", priority=2, timeout=20)
        self._pro = None
        self._cfg = Config()
        self._token = self._cfg.get("data.tushare.token", "") or self._cfg.get(
            "tushare_token", ""
        )
        if self._token:
            self._init_token()

    def _init_token(self):
        """设置 token，失败不影响初始化。"""
        try:
            import tushare as ts  # type: ignore[import-untyped]

            ts.set_token(self._token)
        except Exception as e:
            logger.warning("Tushare token 设置失败: %s", e)

    def _get_pro(self):
        """延迟初始化 pro_api。"""
        if self._pro is not None:
            return self._pro
        try:
            import tushare as ts  # type: ignore[import-untyped]

            if self._token:
                ts.set_token(self._token)
            self._pro = ts.pro_api()
            return self._pro
        except Exception as e:
            logger.warning("Tushare pro_api 初始化失败: %s", e)
            return None

    def _to_tushare_symbol(self, code: str) -> str:
        """将数据库格式 600519 转为 Tushare 格式 600519.SH。"""
        pure = StockCodeNormalizer.to_db(code)
        if pure.startswith(("6", "688", "689", "5", "11", "51")):
            return f"{pure}.SH"
        return f"{pure}.SZ"

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        pro = self._get_pro()
        if pro is None:
            return None
        symbol = self._to_tushare_symbol(code)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        def _call():
            df = pro.daily(
                ts_code=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                return None
            df = df.sort_values("trade_date")
            records = []
            for _, row in df.iterrows():
                records.append({
                    "stock_code": code,
                    "trade_date": self._parse_date(row.get("trade_date")),
                    "open": float(row.get("open", 0) or 0),
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "close": float(row.get("close", 0) or 0),
                    "volume": float(row.get("vol", 0) or 0) * 100,
                    "amount": float(row.get("amount", 0) or 0) * 1000,
                })
            # 取最近 days 条
            return records[-days:]

        try:
            return cast(list[dict] | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("Tushare K线获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        pro = self._get_pro()
        if pro is None:
            return None
        symbol = self._to_tushare_symbol(code)
        trade_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

        def _call():
            # 基础信息
            basic_df = pro.daily_basic(
                ts_code=symbol,
                trade_date=trade_date,
                fields="ts_code,trade_date,close,turnover_rate,pe,pb",
            )
            if basic_df is None or basic_df.empty:
                # 尝试最近交易日
                basic_df = pro.daily_basic(
                    ts_code=symbol,
                    fields="ts_code,trade_date,close,turnover_rate,pe,pb",
                )
                if basic_df is None or basic_df.empty:
                    return None
                basic_df = basic_df.sort_values("trade_date").tail(1)

            row = basic_df.iloc[0]
            return {
                "stock_code": code,
                "stock_name": "",
                "latest_price": float(row.get("close", 0) or 0),
                "change_pct": 0.0,
                "volume": 0.0,
                "amount": 0.0,
                "pe_ratio": float(row.get("pe", 0) or 0),
                "pb_ratio": float(row.get("pb", 0) or 0),
                "turnover_rate": float(row.get("turnover_rate", 0) or 0),
            }

        try:
            return cast(dict | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("Tushare 基本信息获取失败 %s: %s", code, e)
            return None

    def fetch_universe(self) -> list[dict] | None:
        """获取 A 股全市场基础列表。"""
        pro = self._get_pro()
        if pro is None:
            return None

        def _call():
            df = pro.stock_basic(exchange="", list_status="L")
            if df is None or df.empty:
                return None
            stocks = []
            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code", ""))
                if "." not in ts_code:
                    continue
                pure, _ = ts_code.split(".")
                stocks.append({
                    "stock_code": pure,
                    "stock_name": str(row.get("name", "")),
                    "exchange": "SH" if ts_code.endswith(".SH") else "SZ",
                })
            return stocks

        try:
            return cast(list[dict] | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("Tushare 全市场列表获取失败: %s", e)
            return None

    def test_connect(self) -> bool:
        pro = self._get_pro()
        if pro is None:
            return False
        try:
            df = pro.trade_cal(exchange="SSE", start_date="20240101", end_date="20240102")
            return df is not None and not df.empty
        except Exception:
            return False

    @staticmethod
    def _parse_date(value) -> str:
        if value is None:
            return datetime.now().strftime("%Y-%m-%d")
        s = str(value).strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s[:10] if s else datetime.now().strftime("%Y-%m-%d")
