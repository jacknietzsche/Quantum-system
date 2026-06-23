"""东方财富直连数据源适配器（无需 API Key，免费）。

提供：
- A股全市场股票列表
- 日K线（前复权）
- 实时行情快照

数据来源为东方财富公开 HTTP 接口，稳定性较好，可作为 akshare/tushare/tickflow 的降级方案。
"""

from __future__ import annotations

import json
import logging
from typing import cast

from providers.base import SourceAdapter
from providers.normalizer import StockCodeNormalizer

logger = logging.getLogger("ashare-x.providers.eastmoney")


class EastMoneyAdapter(SourceAdapter):
    """东方财富公开接口适配器。"""

    BASE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    UNIVERSE_URL = "https://push2.eastmoney.com/api/qt/clist/get"

    def __init__(self):
        super().__init__(name="eastmoney", priority=3, timeout=15)

    def _to_eastmoney_code(self, code: str) -> str:
        """转换为东方财富格式：market.code（如 1.600519）。"""
        pure = StockCodeNormalizer.to_db(code)
        market = "1" if pure.startswith("6") else "0"
        return f"{market}.{pure}"

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        """获取日K线（前复权）。"""
        secid = self._to_eastmoney_code(code)
        url = (
            f"{self.KLINE_URL}?secid={secid}"
            f"&fields1=f1,f2,f3,f4,f5,f6"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt=1&end=20500101&lmt={days}"
        )

        def _call():
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if not data or data.get("data") is None:
                return None
            klines = data["data"].get("klines") or []
            if not klines:
                return None
            records = []
            for row in klines:
                parts = row.split(",")
                if len(parts) < 9:
                    continue
                try:
                    records.append({
                        "stock_code": code,
                        "trade_date": parts[0][:10],
                        "open": float(parts[1]),
                        "close": float(parts[2]),
                        "high": float(parts[3]),
                        "low": float(parts[4]),
                        "volume": float(parts[5]),
                        "amount": float(parts[6]),
                        "amplitude": float(parts[7]),
                        "change_pct": float(parts[8]),
                        "change_amount": float(parts[9]) if len(parts) > 9 else 0.0,
                        "turnover_rate": float(parts[10]) if len(parts) > 10 else 0.0,
                    })
                except (ValueError, IndexError):
                    continue
            return records if records else None

        try:
            return cast(list[dict] | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("东方财富K线获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        """获取实时行情快照。"""
        secid = self._to_eastmoney_code(code)
        url = (
            f"{self.BASE_URL}?fltt=2&invt=2"
            f"&fields=f12,f13,f14,f2,f3,f4,f5,f6,f9,f10,f18,f20,f21,f23,f26"
            f"&secids={secid}"
        )

        def _call():
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if not data or not data.get("data") or not data["data"].get("diff"):
                return None
            item = next(iter(data["data"]["diff"].values()))
            if not item:
                return None
            return {
                "stock_code": code,
                "stock_name": str(item.get("f14", "")),
                "latest_price": float(item.get("f2", 0) or 0),
                "change_pct": float(item.get("f3", 0) or 0),
                "change_amount": float(item.get("f4", 0) or 0),
                "volume": float(item.get("f5", 0) or 0),
                "amount": float(item.get("f6", 0) or 0),
                "pe_ratio": float(item.get("f9", 0) or 0),
                "pb_ratio": float(item.get("f23", 0) or 0),
                "turnover_rate": float(item.get("f10", 0) or 0),
            }

        try:
            return cast(dict | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("东方财富行情获取失败 %s: %s", code, e)
            return None

    def fetch_universe(self, code: str = "") -> list[dict] | None:
        """获取A股全市场股票列表（沪深主板+科创+创业板）。"""
        # fs 字段含义：
        # m:0+t:6 深圳主板, m:0+t:13 创业板, m:0+t:80 中小板
        # m:1+t:2 上海主板, m:1+t:23 科创板, m:1+t:24 科创板
        fs = "m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:1+t:24"
        url = (
            f"{self.UNIVERSE_URL}?pn=1&pz=6000&po=1&np=1&fltt=2&invt=2"
            f"&fid=f12&fs={fs}&fields=f12,f13,f14"
        )

        def _call():
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if not data or not data.get("data") or not data["data"].get("diff"):
                return None
            stocks = []
            for item in data["data"]["diff"].values():
                code_str = str(item.get("f12", "")).strip()
                name = str(item.get("f14", "")).strip()
                market = str(item.get("f13", "")).strip()
                if not code_str or not code_str.isdigit():
                    continue
                exchange = "SH" if market == "1" else "SZ"
                stocks.append({
                    "stock_code": code_str,
                    "stock_name": name,
                    "exchange": exchange,
                })
            return stocks if stocks else None

        try:
            return cast(list[dict] | None, self._execute_with_retry(_call, max_retries=1))
        except Exception as e:
            logger.warning("东方财富全市场列表获取失败: %s", e)
            return None

    def test_connect(self) -> bool:
        try:
            data = self.fetch_basic("600519")
            if data is None:
                return False
            latest = data.get("latest_price", 0)
            return isinstance(latest, (int, float)) and latest > 0
        except Exception:
            return False

    @staticmethod
    def _parse_javascript_json(text: str) -> dict:
        """解析东方财富部分接口返回的类 JSONP 文本。"""
        if "=" in text:
            text = text.split("=", 1)[1]
        text = text.strip().rstrip(";")
        return cast(dict, json.loads(text))
