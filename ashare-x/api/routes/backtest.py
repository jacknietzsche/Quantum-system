"""回测API路由。

提供向量化回测能力，支持多股票、多策略、基准比较。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("ashare-x.api.backtest")

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    stock_codes: list[str]
    strategy: str = "ma_cross"
    days: int = 250
    initial_capital: float = 1_000_000


class StrategyInfo(BaseModel):
    name: str
    description: str


@router.get("/strategies")
async def list_strategies():
    """返回可用回测策略列表。"""
    return {
        "strategies": [
            StrategyInfo(
                name="ma_cross",
                description="均线交叉策略：5日均线上穿20日均线买入，下穿卖出",
            ),
            StrategyInfo(
                name="rsi",
                description="RSI超买超卖策略：RSI<30买入，RSI>70卖出",
            ),
            StrategyInfo(
                name="bollinger",
                description="布林带策略：价格跌破下轨买入，突破上轨卖出",
            ),
        ]
    }


@router.post("")
async def run_backtest(req: BacktestRequest):
    """执行回测。"""
    if not req.stock_codes:
        raise HTTPException(400, "至少需要一只股票代码")

    if len(req.stock_codes) > 20:
        raise HTTPException(400, "单次回测最多支持20只股票")

    if req.days < 30 or req.days > 500:
        raise HTTPException(400, "回测天数需在30-500之间")

    valid_strategies = {"ma_cross", "rsi", "bollinger"}
    if req.strategy not in valid_strategies:
        raise HTTPException(400, f"不支持策略: {req.strategy}")

    try:
        from services.backtest import VectorbtBacktest

        engine = VectorbtBacktest(initial_capital=req.initial_capital)
        return engine.run(
            stock_codes=req.stock_codes,
            strategy=req.strategy,
            days=req.days,
        )
    except Exception as e:
        logger.error("回测失败: %s", e, exc_info=True)
        raise HTTPException(500, str(e)) from e
