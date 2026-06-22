"""交易计划路由。

提供每日交易计划的查询、触发、持仓查看等API。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("ashare-x.api.trading_plan")

router = APIRouter(prefix="/api/trading-plan", tags=["trading-plan"])

# 后台任务管理
_plan_jobs: dict[str, dict] = {}
_plan_tasks: set[asyncio.Task] = set()


class RunPlanRequest(BaseModel):
    fast_mode: bool = True


class PlanJob(BaseModel):
    job_id: str
    status: str = "running"


@router.get("/today")
async def get_today_plan():
    """获取今日交易计划。"""
    try:
        from services.daily_plan import DailyPlanGenerator

        gen = DailyPlanGenerator()
        plan = gen.get_today_plan()
        if plan:
            return {"ok": True, "plan": plan}
        return {"ok": False, "message": "今日尚未生成交易计划，请点击「运行每日分析」"}
    except Exception as e:
        logger.error("获取今日计划失败: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/history")
async def get_plan_history(limit: int = 30):
    """获取历史交易计划列表。"""
    try:
        from services.daily_plan import DailyPlanGenerator

        gen = DailyPlanGenerator()
        history = gen.get_plan_history(limit=limit)
        return {"ok": True, "history": history, "total": len(history)}
    except Exception as e:
        logger.error("获取历史计划失败: %s", e)
        return {"ok": False, "error": str(e)}


@router.post("/run", response_model=PlanJob)
async def run_daily_plan(req: RunPlanRequest):
    """触发每日计划生成（异步执行）。"""
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _plan_jobs[job_id] = {"job_id": job_id, "status": "running", "result": None}

    task = asyncio.create_task(_run_plan(job_id, req.fast_mode))
    _plan_tasks.add(task)
    task.add_done_callback(_plan_tasks.discard)

    return PlanJob(job_id=job_id, status="running")


@router.get("/run/{job_id}")
async def get_plan_job_status(job_id: str):
    """查询计划生成任务状态。"""
    if job_id not in _plan_jobs:
        return {"ok": False, "error": "Job not found"}
    return _plan_jobs[job_id]


@router.get("/portfolio")
async def get_portfolio():
    """获取当前模拟持仓。"""
    try:
        from services.paper_portfolio import PaperPortfolio

        portfolio = PaperPortfolio()
        account = portfolio.get_account()
        holdings = portfolio.get_holdings()
        return {"ok": True, "account": account, "holdings": holdings}
    except Exception as e:
        logger.error("获取持仓失败: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/trades")
async def get_trades(limit: int = 50):
    """获取模拟交易历史。"""
    try:
        from services.paper_portfolio import PaperPortfolio

        portfolio = PaperPortfolio()
        trades = portfolio.get_trade_history(limit=limit)
        return {"ok": True, "trades": trades, "total": len(trades)}
    except Exception as e:
        logger.error("获取交易历史失败: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/watchlist")
async def get_watchlist():
    """获取当前观察名单。"""
    try:
        from services.market_scanner import MarketScanner

        scanner = MarketScanner()
        watchlist = scanner.get_watchlist()
        return {"ok": True, "watchlist": watchlist, "total": len(watchlist)}
    except Exception as e:
        logger.error("获取观察名单失败: %s", e)
        return {"ok": False, "error": str(e)}


@router.get("/plan/{date}")
async def get_plan_by_date(date: str):
    """获取指定日期的交易计划。"""
    try:
        import json
        import sqlite3

        from core.config import Config

        config = Config()
        db_path = config.get("runtime.db_path", "runtime/investment.db")
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT plan_json FROM daily_plans WHERE id = ?", (date,)
        ).fetchone()
        conn.close()
        if row:
            return {"ok": True, "plan": json.loads(row[0])}
        return {"ok": False, "message": f"未找到 {date} 的交易计划"}
    except Exception as e:
        logger.error("获取计划失败 %s: %s", date, e)
        return {"ok": False, "error": str(e)}


async def _run_plan(job_id: str, fast_mode: bool):
    """后台执行每日计划生成。"""
    job = _plan_jobs[job_id]
    try:
        from services.daily_plan import DailyPlanGenerator

        gen = DailyPlanGenerator()
        plan = gen.generate(fast_mode=fast_mode)
        job["result"] = plan
        job["status"] = "completed"
    except Exception as e:
        logger.error("计划生成失败: %s", e)
        job["status"] = "failed"
        job["error"] = str(e)
