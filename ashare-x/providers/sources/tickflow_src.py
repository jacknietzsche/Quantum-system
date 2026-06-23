"""TickFlow 数据源适配器（支持免费与付费 tier）。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

from core.config import Config
from providers.base import SourceAdapter
from providers.normalizer import StockCodeNormalizer

logger = logging.getLogger("ashare-x.providers.tickflow")


class TickFlowAdapter(SourceAdapter):
    """TickFlow 适配器。

     symbol 格式为 ``600519.SH`` / ``000001.SZ``。
    支持 K 线、基础信息、全市场 symbol 列表。
    """

    def __init__(self):
        super().__init__(name="tickflow", priority=3, timeout=30)
        self._client = None
        self._cfg = Config()
        self._token = self._cfg.get("data.tickflow.token", "") or self._cfg.get(
            "tickflow_token", ""
        )

    def _get_client(self):
        """延迟初始化，失败时返回 None。"""
        if self._client is not None:
            return self._client
        try:
            import tickflow  # type: ignore[import-untyped]

            if self._token:
                self._client = tickflow.TickFlow(api_key=self._token)
            else:
                self._client = tickflow.TickFlow.free()
            return self._client
        except Exception as e:
            logger.warning("TickFlow 初始化失败: %s", e)
            return None

    def _to_tickflow_symbol(self, code: str) -> str:
        """将数据库格式 600519 转为 TickFlow 格式 600519.SH。"""
        pure = StockCodeNormalizer.to_db(code)
        if pure.startswith(("6", "688", "689", "5", "11", "51")):
            return f"{pure}.SH"
        return f"{pure}.SZ"

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        client = self._get_client()
        if client is None:
            return None
        symbol = self._to_tickflow_symbol(code)

        def _call():
            df = client.klines.get(symbol, period="1d", as_dataframe=True)
            if df is None or df.empty:
                return None
            df = df.tail(days).copy()
            df = df.reset_index(drop=True)
            records = []
            for _, row in df.iterrows():
                records.append({
                    "stock_code": code,
                    "trade_date": self._parse_date(row.get("date", row.get("trade_date"))),
                    "open": float(row.get("open", 0) or 0),
                    "high": float(row.get("high", 0) or 0),
                    "low": float(row.get("low", 0) or 0),
                    "close": float(row.get("close", 0) or 0),
                    "volume": float(row.get("volume", 0) or 0),
                    "amount": float(row.get("amount", row.get("turnover", 0)) or 0),
                })
            return records

        try:
            return cast(list[dict] | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("TickFlow K线获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        client = self._get_client()
        if client is None:
            return None
        symbol = self._to_tickflow_symbol(code)

        def _call():
            inst = client.instruments.get(symbol)
            if not inst:
                return None
            # quotes 提供最新行情
            try:
                quote_df = client.quotes.get([symbol], as_dataframe=True)
            except Exception:
                quote_df = None

            latest_price = 0.0
            change_pct = 0.0
            if quote_df is not None and not quote_df.empty:
                row = quote_df.iloc[0]
                latest_price = float(row.get("last_price", 0) or 0)
                change_pct = float(row.get("change_pct", 0) or 0)

            return {
                "stock_code": code,
                "stock_name": inst.get("name", ""),
                "latest_price": latest_price,
                "change_pct": change_pct,
                "pe_ratio": float(inst.get("pe_ratio", 0) or 0),
                "pb_ratio": float(inst.get("pb_ratio", 0) or 0),
                "turnover_rate": float(inst.get("turnover_rate", 0) or 0),
            }

        try:
            return cast(dict | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("TickFlow 基本信息获取失败 %s: %s", code, e)
            return None

    def fetch_universe(self) -> list[dict] | None:
        """获取 A 股全市场 symbol 列表。"""
        client = self._get_client()
        if client is None:
            return None

        def _call():
            df = client.universes.get("a_share", as_dataframe=True)
            if df is None or df.empty:
                return None
            stocks = []
            for _, row in df.iterrows():
                symbol = str(row.get("symbol", ""))
                if "." not in symbol:
                    continue
                pure, _ = symbol.split(".")
                stocks.append({
                    "stock_code": pure,
                    "stock_name": str(row.get("name", "")),
                    "exchange": "SH" if symbol.endswith(".SH") else "SZ",
                })
            return stocks

        try:
            return cast(list[dict] | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("TickFlow 全市场列表获取失败: %s", e)
            return None

    def test_connect(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            _ = client.instruments.get("600519.SH")
            return True
        except Exception:
            return False

    @staticmethod
    def _parse_date(value) -> str:
        if value is None:
            return datetime.now().strftime("%Y-%m-%d")
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        s = str(value)[:10]
        return s if s else datetime.now().strftime("%Y-%m-%d")
