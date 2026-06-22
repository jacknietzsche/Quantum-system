"""绩效归因 API — NAV曲线 + 风险指标 + 收益归因 + 分年度拆解"""

from fastapi import APIRouter, Query

from services.performance import get_performance_engine
from shared.logging import emit_log

router = APIRouter()


@router.get("/metrics")
def get_performance_metrics(
    type: str = Query("value", enum=["limit_up", "momentum", "value"]),
    days: int = Query(250, ge=10, le=1000),
):
    """完整绩效报告: 风险指标 + 归因 + NAV曲线 + 基准对比"""
    try:
        engine = get_performance_engine()
        result = engine.compute_performance(portfolio_type=type, days=days)
        return {"status": result.status, **result.data, "errors": result.errors}
    except Exception as e:
        emit_log("ERROR", "performance_api", f"metrics: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/nav-curve")
def get_nav_curve(
    type: str = Query("value", enum=["limit_up", "momentum", "value"]),
    days: int = Query(250, ge=10, le=1000),
):
    """仅返回NAV曲线(轻量接口, 用于图表渲染)"""
    try:
        engine = get_performance_engine()
        result = engine.get_nav_curve(portfolio_type=type, days=days)
        return {"status": result.status, **result.data}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/yearly")
def get_yearly_breakdown(
    type: str = Query("value", enum=["limit_up", "momentum", "value"]),
):
    """分年度绩效拆解: 年收益/波动率/最大回撤"""
    try:
        engine = get_performance_engine()
        result = engine.get_yearly_breakdown(portfolio_type=type)
        return {"status": result.status, **result.data}
    except Exception as e:
        return {"status": "error", "error": str(e)}
