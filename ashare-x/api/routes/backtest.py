"""回测API路由。

提供向量化回测能力，支持多股票、多策略、基准比较。
"""

from __future__ import annotations

import asyncio
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

        # 加 30s 超时保护，避免底层 K 线网络回源卡死
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: engine.run(
                        stock_codes=req.stock_codes,
                        strategy=req.strategy,
                        days=req.days,
                    ),
                ),
                timeout=30.0,
            )
        except (asyncio.TimeoutError, TimeoutError):
            raise HTTPException(
                504,
                "回测超时（底层 K 线数据获取卡住），请先刷新数据后重试",
            ) from None

        # Frontend expects annualized_return and trades fields
        if "annualized_return" not in result:
            tr_str = str(result.get("total_return", "0%")).replace("%", "")
            try:
                tr = float(tr_str)
                result["annualized_return"] = f"{tr * (250.0 / req.days):.2f}%"
            except ValueError:
                result["annualized_return"] = "0.00%"
        if "trades" not in result:
            trades = []
            for code, metrics in result.get("per_stock", {}).items():
                trades.append({"code": code, **metrics})
            result["trades"] = trades

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("回测失败: %s", e, exc_info=True)
        raise HTTPException(500, str(e)) from e
