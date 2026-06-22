"""持仓API — 3组合模式: 涨停狙击(limit_up), 中期趋势(momentum), 长期价值(value)"""

from fastapi import APIRouter, Query

from services.portfolio import PortfolioService
from shared.logging import emit_log
from shared.models import get_session

router = APIRouter()


def _get_service():
    return PortfolioService(get_session)


@router.get("/holdings")
def get_holdings(type: str = Query("value", enum=["limit_up", "momentum", "value"])):
    try:
        svc = _get_service()
        return svc.get_holdings(type)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_holdings: {e}")
        return {"error": str(e), "positions": [], "cash": 0, "total_asset": 0, "position_count": 0}


@router.get("/summary")
def get_portfolio_summary(type: str = Query("value", enum=["limit_up", "momentum", "value"])):
    try:
        svc = _get_service()
        return svc.get_portfolio_summary(type)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_summary: {e}")
        return {"error": str(e)}


@router.get("/all-summaries")
def get_all_summaries():
    try:
        svc = _get_service()
        return svc.get_all_portfolios_summary()
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_all_summaries: {e}")
        return {"error": str(e)}


@router.post("/holdings")
def add_holding(data: dict):
    """body: {portfolio_type, stock_code, stock_name, buy_price, quantity, buy_reason}"""
    try:
        svc = _get_service()
        return svc.add_position(
            portfolio_type=data.get("portfolio_type", "value"),
            stock_code=data["stock_code"],
            stock_name=data.get("stock_name", ""),
            buy_price=float(data["buy_price"]),
            quantity=int(data["quantity"]),
            buy_date=data.get("buy_date"),
            buy_reason=data.get("buy_reason", ""),
        )
    except Exception as e:
        emit_log("ERROR", "portfolio", f"add_holding: {e}")
        return {"error": str(e)}


@router.put("/holdings/{stock_code}/sell")
def sell_holding(stock_code: str, data: dict):
    """body: {portfolio_type, sell_price, sell_reason}"""
    try:
        svc = _get_service()
        return svc.sell_position(
            portfolio_type=data.get("portfolio_type", "value"),
            stock_code=stock_code,
            sell_price=float(data["sell_price"]),
            sell_date=data.get("sell_date"),
            sell_reason=data.get("sell_reason", ""),
        )
    except Exception as e:
        emit_log("ERROR", "portfolio", f"sell_holding: {e}")
        return {"error": str(e)}


@router.post("/reset")
def reset_portfolio(data: dict):
    """body: {portfolio_type} — if null/empty, reset all"""
    try:
        svc = _get_service()
        return svc.reset_portfolio(portfolio_type=data.get("portfolio_type"))
    except Exception as e:
        emit_log("ERROR", "portfolio", f"reset: {e}")
        return {"error": str(e)}


@router.get("/nav")
def get_nav(
    type: str = Query("value", enum=["limit_up", "momentum", "value"]),
    limit: int = Query(30, ge=1, le=365),
):
    try:
        svc = _get_service()
        return svc.get_nav(type, limit)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_nav: {e}")
        return {"error": str(e), "nav": []}


@router.get("/trades")
def get_trades(
    type: str = Query(None, enum=["limit_up", "momentum", "value"]),
    limit: int = Query(50, ge=1, le=500),
):
    try:
        svc = _get_service()
        return svc.get_trades(portfolio_type=type, limit=limit)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_trades: {e}")
        return {"error": str(e), "data": []}


@router.post("/nav/record")
def record_nav(data: dict):
    """body: {portfolio_type, date}"""
    try:
        svc = _get_service()
        return svc.record_nav(
            portfolio_type=data.get("portfolio_type", "value"),
            date=data.get("date"),
        )
    except Exception as e:
        emit_log("ERROR", "portfolio", f"record_nav: {e}")
        return {"error": str(e)}


@router.get("/holdings-map")
def get_holdings_map(type: str = Query("value", enum=["limit_up", "momentum", "value"])):
    try:
        svc = _get_service()
        return svc.get_holdings_map(type)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_holdings_map: {e}")
        return {"error": str(e)}


# ── 保留的原有端点 ──


@router.get("/stock/{code}")
def get_stock_info(code: str):
    try:
        svc = _get_service()
        return svc.get_stock_info(code)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"get_stock_info: {e}")
        return {"error": str(e)}


@router.get("/search")
def search_stocks(query: str = "", limit: int = Query(20, ge=1, le=100)):
    try:
        svc = _get_service()
        return svc.search_stocks(query, limit)
    except Exception as e:
        emit_log("ERROR", "portfolio", f"search: {e}")
        return {"error": str(e)}
