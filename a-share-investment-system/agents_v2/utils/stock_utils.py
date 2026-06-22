"""股票工具函数 — 参考 TradingAgents-CN/stock_utils.py

提供股票代码识别、分类和处理功能.
支持: A股 (6位数字) / 港股 (4-5位.HK) / 美股 (1-5位字母)
"""

from __future__ import annotations

import re
from enum import Enum

from agents_v2.utils.logging_init import get_logger

logger = get_logger("utils")


class StockMarket(Enum):
    """股票市场枚举"""

    CHINA_A = "china_a"
    HONG_KONG = "hong_kong"
    US = "us"
    UNKNOWN = "unknown"


class StockUtils:
    """股票工具类"""

    @staticmethod
    def identify_market(ticker: str) -> StockMarket:
        """识别股票代码所属市场

        Args:
            ticker: 股票代码

        Returns:
            StockMarket: 股票市场类型
        """
        if not ticker:
            return StockMarket.UNKNOWN

        ticker = str(ticker).strip().upper()

        # 中国A股: 6位数字
        if re.match(r"^\d{6}$", ticker):
            return StockMarket.CHINA_A

        # 港股: 4-5位数字.HK 或纯4-5位数字
        if re.match(r"^\d{4,5}\.HK$", ticker) or re.match(r"^\d{4,5}$", ticker):
            return StockMarket.HONG_KONG

        # 美股: 1-5位字母
        if re.match(r"^[A-Z]{1,5}$", ticker):
            return StockMarket.US

        return StockMarket.UNKNOWN

    @staticmethod
    def is_china_stock(ticker: str) -> bool:
        return StockUtils.identify_market(ticker) == StockMarket.CHINA_A

    @staticmethod
    def is_hk_stock(ticker: str) -> bool:
        return StockUtils.identify_market(ticker) == StockMarket.HONG_KONG

    @staticmethod
    def is_us_stock(ticker: str) -> bool:
        return StockUtils.identify_market(ticker) == StockMarket.US

    @staticmethod
    def get_currency_info(ticker: str) -> tuple[str, str]:
        """获取货币信息 (名称, 符号)"""
        market = StockUtils.identify_market(ticker)
        currency_map = {
            StockMarket.CHINA_A: ("人民币", "¥"),
            StockMarket.HONG_KONG: ("港币", "HK$"),
            StockMarket.US: ("美元", "$"),
        }
        return currency_map.get(market, ("未知", "?"))

    @staticmethod
    def get_data_source(ticker: str) -> str:
        """获取推荐的数据源"""
        market = StockUtils.identify_market(ticker)
        source_map = {
            StockMarket.CHINA_A: "efinance",  # A股用 efinance
            StockMarket.HONG_KONG: "yahoo_finance",
            StockMarket.US: "yahoo_finance",
        }
        return source_map.get(market, "unknown")

    @staticmethod
    def normalize_hk_ticker(ticker: str) -> str:
        """标准化港股代码格式"""
        if not ticker:
            return ticker
        ticker = str(ticker).strip().upper()
        if re.match(r"^\d{4,5}$", ticker):
            return f"{ticker}.HK"
        return ticker

    @staticmethod
    def get_market_info(ticker: str) -> dict:
        """获取完整的市场信息字典"""
        market = StockUtils.identify_market(ticker)
        currency_name, currency_symbol = StockUtils.get_currency_info(ticker)
        data_source = StockUtils.get_data_source(ticker)

        market_names = {
            StockMarket.CHINA_A: "中国A股",
            StockMarket.HONG_KONG: "港股",
            StockMarket.US: "美股",
            StockMarket.UNKNOWN: "未知市场",
        }

        return {
            "ticker": ticker,
            "market": market.value,
            "market_name": market_names[market],
            "currency_name": currency_name,
            "currency_symbol": currency_symbol,
            "data_source": data_source,
            "is_china": market == StockMarket.CHINA_A,
            "is_hk": market == StockMarket.HONG_KONG,
            "is_us": market == StockMarket.US,
        }

    @staticmethod
    def get_board_type(stock_code: str) -> str:
        """获取 A 股板块类型 (主板/创业板/科创板)

        A 股涨跌停规则:
        - 主板: ±10%
        - 创业板 (300xxx): ±20%
        - 科创板 (688xxx): ±20%
        """
        if not stock_code or len(stock_code) < 3:
            return "unknown"
        prefix = stock_code[:3]
        if prefix.startswith("300"):
            return "创业板"
        if prefix.startswith("688"):
            return "科创板"
        if prefix.startswith(("60", "00")):
            return "主板"
        return "其他"

    @staticmethod
    def get_price_limit(board_type: str) -> float:
        """获取涨跌停限制百分比"""
        limit_map = {
            "主板": 0.10,
            "创业板": 0.20,
            "科创板": 0.20,
        }
        return limit_map.get(board_type, 0.10)
