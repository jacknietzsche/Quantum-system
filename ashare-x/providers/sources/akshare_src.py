"""AKShare数据源适配器。"""

from __future__ import annotations

import logging

from providers.base import SourceAdapter

logger = logging.getLogger("ashare-x.providers.akshare")


class AKShareAdapter(SourceAdapter):
    """AKShare适配器（综合数据）。"""

    def __init__(self):
        super().__init__(name="akshare", priority=4, timeout=15)

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        try:
            import akshare as ak

            from providers.normalizer import StockCodeNormalizer

            pure = StockCodeNormalizer.to_db(code)
            df = ak.stock_zh_a_hist(symbol=pure, period="daily", adjust="qfq")
            if df is None or df.empty:
                return None
            df = df.tail(days)
            return [
                {
                    "stock_code": code,
                    "trade_date": str(row["日期"])[:10],
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                    "amount": float(row["成交额"]),
                }
                for _, row in df.iterrows()
            ]
        except ImportError:
            logger.warning("akshare未安装")
            return None
        except Exception as e:
            logger.warning("akshare获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        try:
            import akshare as ak

            from providers.normalizer import StockCodeNormalizer

            pure = StockCodeNormalizer.to_db(code)
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"] == pure]
            if row.empty:
                return None
            row = row.iloc[0]
            stock_name = str(row.get("名称", ""))
            return {
                "stock_code": code,
                "stock_name": stock_name,
                "latest_price": float(row.get("最新价", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "volume": float(row.get("成交量", 0)),
                "amount": float(row.get("成交额", 0)),
                "pe_ratio": float(row.get("市盈率-动态", 0)),
                "pb_ratio": float(row.get("市净率", 0)),
                "turnover_rate": float(row.get("换手率", 0)),
                "is_st": 1 if "ST" in stock_name or "*ST" in stock_name else 0,
            }
        except ImportError:
            return None
        except Exception as e:
            logger.warning("akshare基本面获取失败 %s: %s", code, e)
            return None

    def test_connect(self) -> bool:
        try:
            import akshare as ak

            df = ak.stock_zh_index_daily(symbol="sh000001")
            return df is not None and not df.empty
        except Exception:
            return False
