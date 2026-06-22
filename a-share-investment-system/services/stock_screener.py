"""选股器 — 重构后为薄封装层

内部实现已拆分到 services/screening/ 模块。
公共 API 保持不变。
"""

from services.screening.compat import (
    VALID_STYLES,
    StockScreener,
    classify_stock_category,
)

STOCK_CATEGORIES = {
    "star": "科创板",
    "chinext": "创业板",
    "main": "主板",
    "etf": "ETF",
    "lof": "LOF",
}

__all__ = ["STOCK_CATEGORIES", "VALID_STYLES", "StockScreener", "classify_stock_category"]
