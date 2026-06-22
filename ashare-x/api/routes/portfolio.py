"""持仓路由。

从数据库查询持仓记录，支持再平衡建议。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ashare-x.api.portfolio")

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
async def get_portfolio():
    """获取持仓列表。"""
    try:
        import sqlite3

        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        conn = sqlite3.connect(bus.db_path)

        # 查询持仓表
        try:
            cursor = conn.execute(
                "SELECT stock_code, stock_name, shares, cost_price, current_price "
                "FROM portfolio ORDER BY stock_code"
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # 表不存在
            rows = []

        conn.close()

        holdings = []
        total_assets = 0
        for r in rows:
            stock_code, stock_name, shares, cost_price, current_price = r
            market_value = shares * (current_price or cost_price)
            cost_value = shares * cost_price
            pnl = market_value - cost_value
            pnl_pct = (pnl / cost_value * 100) if cost_value > 0 else 0
            holdings.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "shares": shares,
                "cost_price": cost_price,
                "current_price": current_price,
                "market_value": round(market_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
            total_assets += market_value

        return {
            "holdings": holdings,
            "total_assets": round(total_assets, 2),
            "cash": 0,
            "holding_count": len(holdings),
        }
    except Exception as e:
        logger.error("获取持仓失败: %s", e)
        return {"holdings": [], "total_assets": 0, "cash": 0, "error": str(e)}


@router.post("/portfolio/rebalance")
async def rebalance():
    """再平衡建议。"""
    try:
        from services.market_perception import get_market_state, get_position_cap

        state = get_market_state()
        cap = get_position_cap()

        return {
            "market_state": state,
            "position_cap": f"{cap * 100:.0f}%",
            "operations": [],
            "message": f"当前市场状态: {state}，建议总仓位上限: {cap * 100:.0f}%",
        }
    except Exception as e:
        logger.error("再平衡失败: %s", e)
        return {"operations": [], "error": str(e)}
