"""交易工作流API - 参考TradingAgents设计"""

from fastapi import APIRouter
from pydantic import BaseModel

from services.trading_memory import get_memory, get_reflector
from shared.logging import emit_log

router = APIRouter()


class TradeRecord(BaseModel):
    stock_code: str
    stock_name: str | None = ""
    action: str  # buy, sell, hold
    price: float
    quantity: int
    reasoning: str | None = ""
    portfolio_type: str | None = "value"


class TradeOutcome(BaseModel):
    trade_id: str
    exit_price: float
    pnl: float
    return_pct: float
    reasoning: str | None = ""


@router.get("/memory/trades")
def get_recent_trades(limit: int = 20):
    """获取最近的交易记录"""
    try:
        memory = get_memory()
        trades = memory.get_recent_trades(limit)
        return {"ok": True, "trades": trades}
    except Exception as e:
        emit_log("ERROR", "workflow", f"获取交易记录失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.post("/memory/trades")
def record_trade(trade: TradeRecord):
    """记录交易"""
    try:
        memory = get_memory()
        memory.record_trade(trade.model_dump())
        return {"ok": True, "message": "交易已记录"}
    except Exception as e:
        emit_log("ERROR", "workflow", f"记录交易失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.get("/memory/reflections")
def get_reflections(limit: int = 10):
    """获取反思记录"""
    try:
        memory = get_memory()
        reflections = memory.get_reflections(limit)
        return {"ok": True, "reflections": reflections}
    except Exception as e:
        emit_log("ERROR", "workflow", f"获取反思失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.get("/memory/performance")
def get_performance():
    """获取交易表现分析"""
    try:
        reflector = get_reflector()
        performance = reflector.get_performance_summary()
        learning_points = reflector.get_learning_points()
        return {
            "ok": True,
            "performance": performance,
            "learning_points": learning_points,
        }
    except Exception as e:
        emit_log("ERROR", "workflow", f"获取表现分析失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.get("/memory/lessons")
def get_lessons():
    """获取学习教训"""
    try:
        memory = get_memory()
        lessons = memory.get_lessons()
        return {"ok": True, "lessons": lessons}
    except Exception as e:
        emit_log("ERROR", "workflow", f"获取教训失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.get("/memory/patterns")
def get_patterns():
    """获取交易模式"""
    try:
        memory = get_memory()
        patterns = memory.get_patterns()
        return {"ok": True, "patterns": patterns}
    except Exception as e:
        emit_log("ERROR", "workflow", f"获取模式失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}
