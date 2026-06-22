"""yfinance数据源适配器。"""

from __future__ import annotations

import logging

from providers.base import SourceAdapter

logger = logging.getLogger("ashare-x.providers.yfinance")


class YFinanceAdapter(SourceAdapter):
    """yfinance适配器（美股/港股/全球市场参考）。"""

    def __init__(self):
        super().__init__(name="yfinance", priority=5, timeout=15)

    def fetch_kline(self, code: str, days: int = 365) -> list[dict] | None:
        try:
            import yfinance as yf

            from providers.normalizer import StockCodeNormalizer

            yf_code = StockCodeNormalizer.to_yfinance(code)
            ticker = yf.Ticker(yf_code)
            df = ticker.history(period=f"{days}d")
            if df.empty:
                return None
            return [
                {
                    "stock_code": code,
                    "trade_date": date.strftime("%Y-%m-%d"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                    "amount": float(row["Volume"] * row["Close"]),
                }
                for date, row in df.iterrows()
            ]
        except ImportError:
            logger.warning("yfinance未安装")
            return None
        except Exception as e:
            logger.warning("yfinance获取失败 %s: %s", code, e)
            return None

    def fetch_basic(self, code: str) -> dict | None:
        try:
            import yfinance as yf

            from providers.normalizer import StockCodeNormalizer

            yf_code = StockCodeNormalizer.to_yfinance(code)
            ticker = yf.Ticker(yf_code)
            info = ticker.info
            if not info:
                return None
            return {
                "stock_code": code,
                "stock_name": info.get("shortName", ""),
                "latest_price": info.get("currentPrice", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "pb_ratio": info.get("priceToBook", 0),
                "roe": info.get("returnOnEquity", 0),
            }
        except ImportError:
            return None
        except Exception as e:
            logger.warning("yfinance基本面获取失败 %s: %s", code, e)
            return None

    def test_connect(self) -> bool:
        try:
            import yfinance as yf

            ticker = yf.Ticker("000001.SZ")
            df = ticker.history(period="1d")
            return not df.empty
        except Exception:
            return False
