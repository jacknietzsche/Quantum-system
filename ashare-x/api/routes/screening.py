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
    """获取选股结果（从数据库获取股票数据后多因子打分）。"""
    try:
        from providers.data_bus import DatabaseFirstDataBus
        from services.screening import rank_stocks

        bus = DatabaseFirstDataBus()

        # 从数据库获取所有已缓存的股票
        import sqlite3

        conn = sqlite3.connect(bus.db_path)
        cursor = conn.execute("SELECT stock_code, stock_name FROM stock_info LIMIT 200")
        stocks = [
            {"stock_code": r[0], "stock_name": r[1]}
            for r in cursor.fetchall()
        ]
        conn.close()

        if not stocks:
            return {"stocks": [], "style": style, "message": "数据库无股票数据，请先刷新数据"}

        # 补充基本面数据
        for s in stocks:
            info = bus.get_stock_info(s["stock_code"])
            if info:
                s.update(info)

        # 打分排名
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
