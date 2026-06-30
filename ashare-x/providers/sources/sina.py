"""新浪行情数据源适配器。"""

from __future__ import annotations

import logging

from providers.base import SourceAdapter

logger = logging.getLogger("ashare-x.providers.sina")


class SinaAdapter(SourceAdapter):
    """新浪行情适配器。"""

    BASE_URL = "https://hq.sinajs.cn"
    kline_priority = 0  # K 线优先使用新浪（速度快）

    def __init__(self):
        super().__init__(name="sina", priority=2, timeout=10)
        self.client.headers["Referer"] = "https://finance.sina.com.cn"

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        """新浪K线需要通过money.finance.sina.com.cn获取。"""
        try:
            url = (
                f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                f"CN_MarketData.getKLineData?symbol={self._to_sina_code(code)}"
                f"&scale=240&ma=no&datalen={days}"
            )
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None
            return [
                {
                    "stock_code": code,
                    "trade_date": item.get("day", "")[:10],
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                    "volume": float(item.get("volume", 0)),
                    "amount": 0,
                }
                for item in data
            ]
        except Exception as e:
            logger.warning("新浪K线获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        """获取实时行情。"""
        try:
            url = f"{self.BASE_URL}/list={self._to_sina_code(code)}"
            resp = self.client.get(url)
            resp.raise_for_status()
            text = resp.text
            if "=" not in text:
                return None
            data_str = text.split("=")[1].strip().strip('"').strip(";")
            fields = data_str.split(",")
            if len(fields) < 30:
                return None
            return {
                "stock_code": code,
                "stock_name": fields[0],
                "latest_price": float(fields[3]),
                "change_pct": (
                    (float(fields[3]) - float(fields[2])) / float(fields[2]) * 100
                    if float(fields[2])
                    else 0
                ),
                "volume": float(fields[8]),
                "amount": float(fields[9]),
            }
        except Exception as e:
            logger.warning("新浪行情获取失败 %s: %s", code, e)
            return None

    def test_connect(self) -> bool:
        try:
            resp = self.client.get(f"{self.BASE_URL}/list=sh000001")
            return resp.status_code == 200
        except Exception:
            return False

    def _to_sina_code(self, code: str) -> str:
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)
        exchange = StockCodeNormalizer.get_exchange(code)
        return f"{exchange.lower()}{pure}"
