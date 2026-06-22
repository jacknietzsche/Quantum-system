"""风险监控API - 增强版"""

from fastapi import APIRouter, Query

from shared.logging import emit_log

router = APIRouter()


@router.get("/status")
def risk_status():
    """综合风险状态 - 组合审计 + Kill Switch"""
    try:
        from services.risk_engine import RiskEngine
        from services.trade_executor import TradeExecutor

        re = RiskEngine()
        te = TradeExecutor()
        positions_result = te.get_positions()
        positions = positions_result.data.get("positions", []) if positions_result.data else []
        audit = re.full_audit(positions).data
        ks = te.check_kill_switch().data
        return {"audit": audit, "kill_switch": ks}
    except Exception as e:
        emit_log("ERROR", "risk", f"risk_status: {e}")
        return {"error": str(e)}


@router.get("/alerts")
def risk_alerts():
    """风险预警列表 - 止损/止盈/集中度/行业预警"""
    try:
        from services.data_bus import DatabaseBackedDataBus
        from services.market_perception import MarketPerception
        from services.risk_engine import RiskEngine
        from services.trade_executor import TradeExecutor

        re = RiskEngine()
        te = TradeExecutor()
        positions_result = te.get_positions()
        positions = positions_result.data.get("positions", []) if positions_result.data else []

        # 获取市场状态
        mp = MarketPerception()
        data_bus = DatabaseBackedDataBus()
        breadth = data_bus.get_market_breadth()
        indices = data_bus.get_market_indices()
        regime = mp.perceive({"breadth": breadth or {}, "indices": indices or {}}).data

        alerts_result = re.risk_alerts(positions, regime)
        return alerts_result.data if alerts_result.data else {"alerts": [], "total_alerts": 0}
    except Exception as e:
        emit_log("ERROR", "risk", f"risk_alerts: {e}")
        return {"error": str(e), "alerts": []}


@router.post("/assess-stock")
def assess_stock_risk(data: dict):
    """个股风险评估 - 波动率/估值/流动性/财务"""
    try:
        from services.risk_engine import RiskEngine
        from shared.db_session import db_session
        from shared.models import StockInfo

        stock_code = data.get("stock_code", "")
        if not stock_code:
            return {"error": "stock_code is required"}

        # 从数据库获取股票数据
        stock_data = {}
        with db_session() as session:
            info = session.query(StockInfo).filter_by(stock_code=stock_code).first()
            if info:
                stock_data = {
                    "pe": float(info.pe_ratio or 0),
                    "roe": float(info.roe or 0),
                    "debt_to_equity": float(info.debt_to_equity or 0),
                    "market_cap": float(info.total_market_cap or 0) / 100000000
                    if info.total_market_cap
                    else 0,
                    "gross_margin": float(info.gross_margin or 0),
                }

        # 合并用户传入的数据
        stock_data.update({k: v for k, v in data.items() if k != "stock_code"})

        re = RiskEngine()
        result = re.assess_stock_risk(stock_code, stock_data)
        return result.data if result.data else {"error": result.errors}
    except Exception as e:
        emit_log("ERROR", "risk", f"assess_stock: {e}")
        return {"error": str(e)}


@router.get("/portfolio-var")
def portfolio_var(confidence: float = Query(0.95, ge=0.90, le=0.99)):
    """组合VaR计算 - 历史模拟法 + 参数法"""
    try:
        from services.risk_engine import RiskEngine
        from services.trade_executor import TradeExecutor

        re = RiskEngine()
        te = TradeExecutor()
        positions_result = te.get_positions()
        positions = positions_result.data.get("positions", []) if positions_result.data else []

        result = re.portfolio_var(positions, confidence=confidence)
        return result.data if result.data else {"error": result.errors}
    except Exception as e:
        emit_log("ERROR", "risk", f"portfolio_var: {e}")
        return {"error": str(e)}


@router.get("/stress-test")
def stress_test():
    """压力测试 - 模拟极端回撤场景"""
    try:
        from services.risk_engine import RiskEngine
        from services.trade_executor import TradeExecutor

        re = RiskEngine()
        te = TradeExecutor()
        positions_result = te.get_positions()
        positions = positions_result.data.get("positions", []) if positions_result.data else []

        audit = re.full_audit(positions)
        return audit.data.get("portfolio_risk", {}).get("stress_test", {}) if audit.data else {}
    except Exception as e:
        emit_log("ERROR", "risk", f"stress_test: {e}")
        return {"error": str(e)}
