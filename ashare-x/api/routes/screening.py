"""选股路由。

通过DatabaseFirstDataBus获取数据，调用screening服务进行多因子选股。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("ashare-x.api.screening")

router = APIRouter(prefix="/api", tags=["screening"])


class ScreeningResult(BaseModel):
    stock_code: str
    stock_name: str = ""
    score: float
    rank: int
    factors: dict = {}


@router.get("/screening")
async def get_screening(style: str = "balanced", limit: int = 20):
    """获取选股结果（一次性查 DB 全字段，避免循环调网络 API）。"""
    try:
        import sqlite3

        from providers.data_bus import DatabaseFirstDataBus
        from services.screening import rank_stocks

        bus = DatabaseFirstDataBus()

        # 一次查询 stock_info 表所有字段，避免循环调 bus.get_stock_info 触发网络回源
        conn = sqlite3.connect(bus.db_path)
        try:
            cursor = conn.execute(
                "SELECT stock_code, stock_name, category, industry, pe_ratio, "
                "pb_ratio, roe, latest_price, change_pct, volume, amount, "
                "turnover_rate, ma5, ma20, ma60, rsi_14, macd "
                "FROM stock_info LIMIT 200"
            )
            col_names = [d[0] for d in cursor.description]
            stocks = [
                {name: val for name, val in zip(col_names, row)}
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

        if not stocks:
            return {"stocks": [], "style": style, "message": "数据库无股票数据，请先刷新数据"}

        # 打分排名（rank_stocks 内部会基于已有字段计算 value/growth/momentum/quality 分数）
        ranked = rank_stocks(stocks, style=style, top_n=limit)

        results = [
            {
                "stock_code": s.get("stock_code", ""),
                "stock_name": s.get("stock_name", ""),
                "score": round(s.get("score", 0), 2),
                "rank": i + 1,
                "factors": {
                    "value": round(s.get("value_score", 0), 2),
                    "growth": round(s.get("growth_score", 0), 2),
                    "momentum": round(s.get("momentum_score", 0), 2),
                    "quality": round(s.get("quality_score", 0), 2),
                },
            }
            for i, s in enumerate(ranked)
        ]

        return {"stocks": results, "style": style, "total": len(results)}
    except Exception as e:
        logger.error("选股失败: %s", e)
        return {"stocks": [], "style": style, "error": str(e)}


@router.post("/screening/run")
async def run_screening(style: str = "balanced"):
    """执行选股流程。"""
    return await get_screening(style=style, limit=50)
