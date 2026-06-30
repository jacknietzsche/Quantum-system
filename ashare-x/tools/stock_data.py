"""股票数据获取工具。

设计依据: S04 §4.6, experiments exp6.1。
通过DatabaseFirstDataBus获取数据。
"""

from __future__ import annotations

import logging

import pandas as pd

from providers.data_bus import DatabaseFirstDataBus
from tools.technical_indicators import compute_indicators, get_latest_indicators

logger = logging.getLogger(__name__)

_bus = DatabaseFirstDataBus()


def get_stock_data(code: str, days: int = 365) -> dict:
    """
    获取股票数据（K线+技术指标）。
    返回: {kline: DataFrame, indicators: dict}
    """
    kline = _bus.get_kline(code, days)
    if kline is None or (isinstance(kline, pd.DataFrame) and kline.empty) or (isinstance(kline, list) and len(kline) == 0):
        return {"kline": None, "indicators": None}

    # bus.get_kline returns list[dict]; convert to DataFrame for indicator calc
    df = pd.DataFrame(kline) if not isinstance(kline, pd.DataFrame) else kline
    if df.empty:
        return {"kline": None, "indicators": None}

    # 计算技术指标
    kline_with_indicators = compute_indicators(df)
    indicators = get_latest_indicators(df)

    return {
        "kline": kline_with_indicators,
        "indicators": indicators,
    }


def get_indicators(code: str) -> dict | None:
    """仅获取技术指标（不返回K线数据）。"""
    data = get_stock_data(code)
    return data.get("indicators")
