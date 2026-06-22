"""市场感知服务。

设计依据: S06 §6.3, S08 §8.2。
通过DatabaseFirstDataBus获取市场概览数据（数据库优先 → API → 存库 → 返回）。
"""

from __future__ import annotations

import logging

from providers.data_bus import DatabaseFirstDataBus

logger = logging.getLogger("ashare-x.services.market_perception")

_bus = DatabaseFirstDataBus()


def get_market_overview() -> dict:
    """
    获取市场概览（数据库优先）。
    返回: {indices, market_state, north_flow, advance_count, decline_count}
    """
    return _bus.get_market_overview()


def get_market_state() -> str:
    """获取当前市场状态: BULL/NEUTRAL/BEAR/PANIC。"""
    overview = get_market_overview()
    state = overview.get("market_state", "NEUTRAL")
    return str(state) if state is not None else "NEUTRAL"


def get_position_cap() -> float:
    """根据当前市场状态获取建议仓位上限。"""
    from tools.market_state import get_position_cap as _get_cap

    state = get_market_state()
    return _get_cap(state)
