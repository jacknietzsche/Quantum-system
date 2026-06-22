"""基本面数据获取工具。

设计依据: S04 §4.6, S05 §5.11。
通过DatabaseFirstDataBus获取数据（数据库优先 → API → 存库 → 返回）。
"""

from __future__ import annotations

import logging

from providers.data_bus import DatabaseFirstDataBus

logger = logging.getLogger(__name__)

_bus = DatabaseFirstDataBus()


def get_fundamentals(code: str) -> dict | None:
    """
    获取基本面数据（数据库优先）。
    返回: {pe_ratio, pb_ratio, roe, revenue_growth, profit_growth, ...}
    """
    return _bus.get_fundamentals(code)


def get_financial_statements(code: str) -> dict | None:
    """获取财务报表指标（数据库优先）。"""
    return _bus.get_financial_statements(code)
