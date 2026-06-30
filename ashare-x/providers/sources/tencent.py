"""腾讯行情数据源适配器。

设计依据: S05 §5.7, 现有系统 providers/sources/tencent.py。
腾讯行情API: 实时行情、K线、基本面。
"""

from __future__ import annotations

import logging

from providers.base import SourceAdapter

logger = logging.getLogger("ashare-x.providers.tencent")


class TencentAdapter(SourceAdapter):
    """腾讯行情适配器。"""

    BASE_URL = "https://qt.gtimg.cn"
    KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    kline_priority = 1  # K 线新浪失败后 fallback 到腾讯

    def __init__(self):
        super().__init__(name="tencent", priority=1, timeout=10)

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        """获取K线数据（使用腾讯K线API，非实时快照）。"""
        try:
            tencent_code = self._to_tencent_code(code)
            # 请求日K前复权数据，最多640根
            url = (
                f"{self.KLINE_URL}?param={tencent_code},day,,,"
                f"{min(days, 640)},qfq"
            )
            resp = self.client.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if not data or "data" not in data:
                return None

            stock_data = data["data"].get(tencent_code, {})
            # 优先取前复权数据
            kline_list = stock_data.get("qfqday") or stock_data.get("day")
            if not kline_list:
                return None

            result: list[dict] = []
            for row in kline_list:
                if len(row) < 6:
                    continue
                try:
                    result.append({
                        "stock_code": code,
                        "trade_date": str(row[0])[:10],
                        "open": float(row[1]),
                        "high": float(row[3]),
                        "low": float(row[4]),
                        "close": float(row[2]),
                        "volume": float(row[5]),
                        "amount": float(row[5]) * float(row[2]) if len(row) < 8 else float(row[7]),
                    })
                except (ValueError, IndexError):
                    continue

            if not result:
                return None

            logger.debug("腾讯K线获取成功 %s: %d条", code, len(result))
            return result

        except Exception as e:
            logger.warning("腾讯K线获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        """获取基本面数据（实时行情快照）。"""
        try:
            url = f"{self.BASE_URL}/q={self._to_tencent_code(code)}"
            resp = self.client.get(url, timeout=10)
            resp.raise_for_status()
            text = resp.text
            if "=" not in text:
                return None
            data_str = text.split("=")[1].strip().strip('"').strip(";")
            fields = data_str.split("~")
            if len(fields) < 45:
                return None
            return {
                "stock_code": code,
                "stock_name": fields[1] if len(fields) > 1 else "",
                "latest_price": float(fields[3]) if fields[3] else 0,
                "change_pct": float(fields[32]) if fields[32] else 0,
                "volume": float(fields[6]) if fields[6] else 0,
                "amount": float(fields[37]) if fields[37] else 0,
                "pe_ratio": float(fields[39]) if fields[39] else 0,
                "pb_ratio": float(fields[46]) if len(fields) > 46 and fields[46] else 0,
                "turnover_rate": float(fields[38]) if len(fields) > 38 and fields[38] else 0,
            }
        except Exception as e:
            logger.warning("腾讯基本面获取失败 %s: %s", code, e)
            return None

    def test_connect(self) -> bool:
        """健康检查。"""
        try:
            resp = self.client.get(f"{self.BASE_URL}/q=sh000001", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _to_tencent_code(self, code: str) -> str:
        """转换为腾讯格式: sh600519"""
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)
        exchange = StockCodeNormalizer.get_exchange(code)
        return f"{exchange.lower()}{pure}"
