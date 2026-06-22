"""统一数据库查询辅助层 — 封装各模块常见查询模式 + 写入函数"""

import json
from datetime import datetime

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from shared.models import (
    AnalysisTask,
    DailyNAV,
    KlineCache,
    MarketSnapshot,
    Order,
    OrderDirection,
    OrderStatus,
    Portfolio,
    StockInfo,
    SystemLog,
    Trade,
    TradeRecord,
    TradeStatus,
    TradeType,
    Watchlist,
)


def get_stock_by_code(session: Session, code: str) -> StockInfo | None:
    return session.query(StockInfo).filter_by(stock_code=code).first()


def get_stock_by_code_batch(session: Session, codes: list[str]) -> dict[str, StockInfo]:
    rows = session.query(StockInfo).filter(StockInfo.stock_code.in_(codes)).all()
    return {r.stock_code: r for r in rows}


def search_stocks(session: Session, keyword: str, limit: int = 50) -> list[StockInfo]:
    q = f"%{keyword}%"
    return (
        session.query(StockInfo)
        .filter((StockInfo.stock_code.like(q)) | (StockInfo.stock_name.like(q)))
        .limit(limit)
        .all()
    )


def list_active_holdings(session: Session) -> list[Portfolio]:
    return session.query(Portfolio).filter_by(status=TradeStatus.HOLDING).all()


def get_portfolio_summary(session: Session) -> dict:
    holdings = list_active_holdings(session)
    total_cost = sum(h.cost_value for h in holdings)
    total_value = sum(h.current_value for h in holdings)
    total_pl = sum(h.profit_loss for h in holdings)
    return {
        "count": len(holdings),
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pl": round(total_pl, 2),
        "total_pl_pct": round(total_pl / total_cost * 100, 2) if total_cost else 0,
        "holdings": holdings,
    }


def get_price_map(session: Session, codes: list[str]) -> dict[str, float]:
    rows = (
        session.query(StockInfo.stock_code, StockInfo.latest_price)
        .filter(StockInfo.stock_code.in_(codes))
        .all()
    )
    return {r[0]: r[1] or 0 for r in rows}


def get_market_cap_map(session: Session, codes: list[str]) -> dict[str, float]:
    rows = (
        session.query(StockInfo.stock_code, StockInfo.total_market_cap)
        .filter(StockInfo.stock_code.in_(codes))
        .all()
    )
    return {r[0]: r[1] or 0 for r in rows}


def get_kline_data(session: Session, code: str, days: int = 60) -> list[KlineCache]:
    return (
        session.query(KlineCache)
        .filter_by(stock_code=code)
        .order_by(KlineCache.trade_date.desc())
        .limit(days)
        .all()
    )


def get_latest_kline_date(session: Session, code: str) -> str | None:
    row = (
        session.query(KlineCache.trade_date)
        .filter_by(stock_code=code)
        .order_by(KlineCache.trade_date.desc())
        .first()
    )
    return row[0] if row else None


def get_snapshot(session: Session, snapshot_type: str) -> MarketSnapshot | None:
    return session.query(MarketSnapshot).filter_by(snapshot_type=snapshot_type).first()


def upsert_snapshot(session: Session, snapshot_type: str, data_json: str, trade_date: str = ""):
    existing = get_snapshot(session, snapshot_type)
    if existing:
        existing.data_json = data_json
        existing.trade_date = trade_date or existing.trade_date
        existing.updated_at = datetime.now()
    else:
        snap = MarketSnapshot(
            snapshot_type=snapshot_type,
            data_json=data_json,
            trade_date=trade_date,
            updated_at=datetime.now(),
        )
        session.add(snap)


def get_watchlist_codes(session: Session) -> list[str]:
    rows = session.query(Watchlist.stock_code).all()
    return [r[0] for r in rows]


def get_analysis_task(session: Session, task_id: str) -> AnalysisTask | None:
    return session.query(AnalysisTask).filter_by(task_id=task_id).first()


def list_pending_tasks(session: Session, limit: int = 20) -> list[AnalysisTask]:
    return (
        session.query(AnalysisTask)
        .filter_by(status="pending")
        .order_by(AnalysisTask.created_at.asc())
        .limit(limit)
        .all()
    )


def get_recent_trade_records(session: Session, code: str, limit: int = 20) -> list[TradeRecord]:
    return (
        session.query(TradeRecord)
        .filter_by(stock_code=code)
        .order_by(TradeRecord.trade_date.desc())
        .limit(limit)
        .all()
    )


def get_daily_nav_range(session: Session, days: int = 30) -> list[DailyNAV]:
    return session.query(DailyNAV).order_by(DailyNAV.date.desc()).limit(days).all()


def count_stocks(session: Session) -> int:
    return session.query(func.count(StockInfo.id)).scalar() or 0


def get_stock_quality_stats(session: Session) -> dict:
    total = count_stocks(session)
    if not total:
        return {"total": 0}
    no_price = (
        session.query(StockInfo)
        .filter((StockInfo.latest_price == 0) | (StockInfo.latest_price.is_(None)))
        .count()
    )
    no_industry = (
        session.query(StockInfo)
        .filter((StockInfo.industry == "") | (StockInfo.industry.is_(None)))
        .count()
    )
    no_name = (
        session.query(StockInfo)
        .filter(
            (StockInfo.stock_name == "")
            | (StockInfo.stock_name.is_(None))
            | (StockInfo.stock_name == StockInfo.stock_code)
        )
        .count()
    )
    complete = total - max(no_price, no_industry, no_name)
    return {
        "total": total,
        "with_price": total - no_price,
        "with_industry": total - no_industry,
        "with_name": total - no_name,
        "completeness_pct": round(complete / total * 100, 1),
    }


def log_system_event(session: Session, module: str, level: str, message: str):
    log = SystemLog(module=module, level=level, message=message)
    session.add(log)


def get_recent_logs(session: Session, limit: int = 50, level: str | None = None) -> list[SystemLog]:
    q = session.query(SystemLog)
    if level:
        q = q.filter_by(level=level)
    return q.order_by(SystemLog.created_at.desc()).limit(limit).all()


def table_row_count(session: Session, table_name: str) -> int:
    """安全统计表行数,只允许预定义表名"""
    safe_names = {
        "stock_info": "stock_info",
        "kline_cache": "kline_cache",
        "portfolio": "portfolio",
        "trade_records": "trade_records",
        "orders": "orders",
        "trades": "trades",
        "daily_nav": "daily_nav",
        "system_logs": "system_logs",
        "watchlist": "watchlist",
        "market_snapshot": "market_snapshot",
        "daily_reports": "daily_reports",
    }
    table = safe_names.get(table_name.strip('"[]` '))
    if not table:
        raise ValueError(f"不安全的表名: {table_name}")
    from sqlalchemy import func, select

    stmt = select(func.count()).select_from(text(table))
    return session.execute(stmt).scalar() or 0


# ════════════════════════════════════════════
#  写入函数
# ════════════════════════════════════════════


def add_holding(
    session: Session,
    stock_code: str,
    stock_name: str,
    buy_date: str,
    buy_price: float,
    quantity: int,
    buy_reason: str = "",
) -> Portfolio:
    existing = (
        session.query(Portfolio)
        .filter_by(stock_code=stock_code, status=TradeStatus.HOLDING)
        .first()
    )
    if existing:
        existing.quantity += quantity
        existing.buy_reason = buy_reason or existing.buy_reason
        existing.updated_at = datetime.now()
        return existing
    p = Portfolio(
        stock_code=stock_code,
        stock_name=stock_name,
        buy_date=buy_date,
        buy_price=buy_price,
        quantity=quantity,
        buy_reason=buy_reason,
        current_price=buy_price,
    )
    session.add(p)
    return p


def sell_holding(
    session: Session,
    stock_code: str,
    sell_date: str,
    sell_price: float,
    quantity: int | None = None,
    sell_reason: str = "",
):
    holding = (
        session.query(Portfolio)
        .filter_by(stock_code=stock_code, status=TradeStatus.HOLDING)
        .first()
    )
    if not holding:
        return None
    qty = quantity if quantity else holding.quantity
    if qty >= holding.quantity:
        holding.status = TradeStatus.SOLD
        holding.quantity = 0
    else:
        holding.quantity -= qty
    holding.sell_date = sell_date
    holding.sell_price = sell_price
    holding.sell_reason = sell_reason
    holding.updated_at = datetime.now()
    return holding


def update_holding_price(session: Session, stock_code: str, current_price: float):
    holdings = (
        session.query(Portfolio).filter_by(stock_code=stock_code, status=TradeStatus.HOLDING).all()
    )
    for h in holdings:
        h.current_price = current_price
        h.updated_at = datetime.now()


def add_trade_record(
    session: Session,
    stock_code: str,
    stock_name: str,
    trade_date: str,
    trade_type: TradeType,
    price: float,
    quantity: int,
    reason: str = "",
):
    tr = TradeRecord(
        stock_code=stock_code,
        stock_name=stock_name,
        trade_date=trade_date,
        trade_type=trade_type,
        price=price,
        quantity=quantity,
        amount=price * quantity,
        reason=reason,
    )
    session.add(tr)
    return tr


def create_order(
    session: Session,
    stock_code: str,
    stock_name: str,
    direction: OrderDirection,
    quantity: int,
    target_date: str,
    price_type: str = "open",
    limit_price: float = 0,
    signal_confidence: float = 0,
    signal_reason: str = "",
) -> Order:
    o = Order(
        stock_code=stock_code,
        stock_name=stock_name,
        direction=direction,
        quantity=quantity,
        price_type=price_type,
        limit_price=limit_price,
        target_date=target_date,
        signal_confidence=signal_confidence,
        signal_reason=signal_reason,
    )
    session.add(o)
    return o


def update_order_status(
    session: Session,
    order_id: int,
    status: OrderStatus,
    filled_price: float = 0,
    filled_quantity: int = 0,
):
    o = session.query(Order).filter_by(id=order_id).first()
    if o:
        o.status = status
        o.filled_price = filled_price
        o.filled_quantity = filled_quantity
        if status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            o.executed_at = datetime.now()


def create_trade(
    session: Session,
    order_id: int,
    stock_code: str,
    stock_name: str,
    direction: OrderDirection,
    execute_price: float,
    quantity: int,
    trade_date: str,
    commission: float = 0,
    tax: float = 0,
) -> Trade:
    t = Trade(
        order_id=order_id,
        stock_code=stock_code,
        stock_name=stock_name,
        direction=direction,
        execute_price=execute_price,
        quantity=quantity,
        amount=execute_price * quantity,
        commission=commission,
        tax=tax,
        trade_date=trade_date,
    )
    session.add(t)
    return t


def update_task_status(
    session: Session,
    task_id: str,
    status: str | None = None,
    signal: str | None = None,
    confidence: int | None = None,
    progress: int | None = None,
    result_json: str | None = None,
    error: str | None = None,
):
    t = session.query(AnalysisTask).filter_by(task_id=task_id).first()
    if not t:
        return None
    if status is not None:
        t.status = status
        if status in ("completed", "failed"):
            t.finished_at = datetime.now()
    if signal is not None or confidence is not None:
        raw = t.result_json if isinstance(t.result_json, str) else "{}"
        try:
            data = json.loads(raw or "{}")
        except (json.JSONDecodeError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        if signal is not None:
            data["signal"] = signal
        if confidence is not None:
            data["confidence"] = confidence
        t.result_json = json.dumps(data, ensure_ascii=False)
    if progress is not None:
        t.progress = progress
    if result_json is not None:
        t.result_json = result_json
    if error is not None:
        t.error_msg = error
    return t


def create_analysis_task(session: Session, stock_code: str, stock_name: str = "") -> AnalysisTask:
    t = AnalysisTask(stock_code=stock_code, stock_name=stock_name or stock_code)
    session.add(t)
    session.flush()
    return t


def upsert_daily_nav(
    session: Session,
    date: str,
    total_asset: float,
    cash: float = 0,
    stock_value: float = 0,
    position_count: int = 0,
    notes: str = "",
):
    existing = session.query(DailyNAV).filter_by(date=date).first()
    if existing:
        existing.total_asset = total_asset
        existing.cash = cash
        existing.stock_value = stock_value
        existing.position_count = position_count
        existing.notes = notes or existing.notes
        return existing
    nav = DailyNAV(
        date=date,
        total_asset=total_asset,
        cash=cash,
        stock_value=stock_value,
        position_count=position_count,
        notes=notes,
    )
    session.add(nav)
    return nav


def batch_update_stock_category(session: Session):
    """按代码前缀批量更新所有 stock_info.category 字段"""
    stocks = session.query(StockInfo).all()
    for s in stocks:
        code = s.stock_code
        if code.startswith(("51", "56", "58", "59", "15")):
            cat = "ETF"
        elif code.startswith("16"):
            cat = "LOF"
        else:
            cat = "股票"
        if s.category != cat:
            s.category = cat
    return True
