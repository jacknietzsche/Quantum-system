"""社交情绪数据工具。

设计依据: S04 §4.6, S05 §5.11。
通过DatabaseFirstDataBus获取数据（数据库优先 → API → 存库 → 返回）。
获取龙虎榜、北向资金、融资融券、资金流向数据。
"""

from __future__ import annotations

import logging

from providers.data_bus import DatabaseFirstDataBus

logger = logging.getLogger(__name__)

_bus = DatabaseFirstDataBus()


def get_social_sentiment(code: str) -> dict:
    """
    获取情绪数据（数据库优先）。
    返回: {north_flow, dragon_tiger, turnover_rate, fund_flow}
    """
    return _bus.get_social_sentiment(code)


def get_market_breadth() -> dict:
    """
    获取市场广度数据（数据库优先）。
    返回: {total, up, down, flat, limit_up, limit_down, up_ratio}
    """
    return _bus.get_market_breadth()
