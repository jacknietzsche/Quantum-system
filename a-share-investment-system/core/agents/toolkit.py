"""DB-first cache-through 数据工具 — 参考 TradingAgents agent_utils.py"""

from datetime import datetime

from providers.market_data import MarketDataProvider
from shared.logging import emit_log
from shared.models import KlineCache, StockInfo, get_session

_provider = None


def _get_provider():
    global _provider  # noqa: PLW0603
    if _provider is None:
        _provider = MarketDataProvider()
    return _provider


def get_stock_data(code: str) -> dict:
    """获取个股行情 — DB优先"""
    session = get_session()
    try:
        info = session.query(StockInfo).filter_by(stock_code=code).first()
        # 如果6小时内无数据, 尝试刷新
        if (
            not info
            or not info.latest_price
            or not info.updated_at
            or (datetime.now() - info.updated_at).total_seconds() > 21600
        ):
            session.close()
            try:
                raw = _get_provider().get_stock_basic(code)
                if raw:
                    from services.data_initializer import DataInitializer

                    DataInitializer()._save_stock_info(code, raw)
            except Exception as e:
                emit_log("WARNING", "toolkit", f"Operation failed: {str(e)[:100]}")
            session = get_session()
            info = session.query(StockInfo).filter_by(stock_code=code).first()
        if info:
            return {
                "stock_code": info.stock_code,
                "stock_name": info.stock_name,
                "price": info.latest_price,
                "change_pct": info.change_pct,
                "industry": info.industry,
                "pe": info.pe_ratio,
            }
        return {}
    finally:
        session.close()


def get_indicators(code: str, days: int = 60) -> dict:
    """获取技术指标 — DB优先"""
    session = get_session()
    try:
        count = session.query(KlineCache).filter_by(stock_code=code).count()
        if count < days:
            session.close()
            try:
                df = _get_provider().get_stock_kline(code, days)
                if df is not None and not df.empty:
                    from services.data_initializer import DataInitializer

                    DataInitializer()._save_klines(code, df)
            except Exception as e:
                emit_log("WARNING", "toolkit", f"Operation failed: {str(e)[:100]}")
        session = get_session()
        info = session.query(StockInfo).filter_by(stock_code=code).first()
        if info:
            return {
                "ma5": info.ma5,
                "ma10": info.ma10,
                "ma20": info.ma20,
                "ma60": info.ma60,
                "rsi_14": info.rsi_14,
                "volatility": info.volatility_20d,
                "trend": info.trend,
                "turnover_rate": info.turnover_rate,
            }
        return {}
    finally:
        session.close()


def get_fundamentals(code: str) -> dict:
    """获取基本面 — DB优先"""
    session = get_session()
    try:
        info = session.query(StockInfo).filter_by(stock_code=code).first()
        if info:
            return {
                "roe": info.roe,
                "eps": info.eps,
                "bvps": info.bvps,
                "gross_margin": info.gross_margin,
                "debt_to_equity": info.debt_to_equity,
                "pe_ratio": info.pe_ratio,
                "pb_ratio": info.pb_ratio,
            }
        return {}
    finally:
        session.close()


def get_market_regime() -> str:
    """获取大盘环境"""
    from providers.database import get_session as db_session_factory
    from services.market import MarketService

    svc = MarketService(db_session_factory)
    try:
        indices = svc.get_indices()
        if indices and "indices" in indices:
            sh = next(
                (
                    i
                    for i in indices["indices"]
                    if i.get("code") == "000001" or i.get("name", "").startswith("上证")
                ),
                None,
            )
            if sh:
                chg = sh.get("change_pct", 0)
                if chg > 1:
                    return "bullish"
                if chg < -1:
                    return "bearish"
        return "neutral"
    except Exception as e:
        emit_log("WARNING", "toolkit", f"Operation failed: {str(e)[:100]}")
        return "neutral"
