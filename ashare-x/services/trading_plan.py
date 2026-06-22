"""交易计划生成。

设计依据: S08 §8.3。
将Agent决策转化为可执行的交易计划。
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)


def generate_trading_plan(
    ticker: str,
    stock_name: str,
    action: str,
    confidence: float,
    current_price: float,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    position_pct: float | None = None,
    thesis: str = "",
    key_factors: list[str] | None = None,
    risks: list[str] | None = None,
) -> dict:
    """生成交易计划。"""
    price = Decimal(str(current_price))

    if entry_price is None:
        entry_price = float(price)
    if stop_loss is None:
        stop_loss = float(
            (price * Decimal("0.95")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
    if take_profit is None:
        take_profit = float(
            (price * Decimal("1.15")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
    if position_pct is None:
        position_pct = 5.0

    return {
        "ticker": ticker,
        "stock_name": stock_name,
        "action": action,
        "confidence": confidence,
        "current_price": current_price,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "position_pct": position_pct,
        "thesis": thesis,
        "key_factors": key_factors or [],
        "risks": risks or [],
        "invalidation": f"跌破{stop_loss}止损",
    }
