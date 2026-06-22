"""Market domain models -- StockInfo, KlineCache, MarketSnapshot, DragonTiger, FundMetricHist"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.models._base import Base


class StockInfo(Base):
    """Stock fundamental + technical + screening data"""

    __tablename__ = "stock_info"
    __table_args__: tuple | dict | None = None

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(10), default="股票")
    industry: Mapped[str] = mapped_column(String(50), default="")
    pe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    pb_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    gross_margin: Mapped[float] = mapped_column(Float, default=0.0)
    net_margin: Mapped[float] = mapped_column(Float, default=0.0)
    roe: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    total_market_cap: Mapped[float] = mapped_column(Float, default=0.0)
    float_market_cap: Mapped[float] = mapped_column(Float, default=0.0)
    latest_price: Mapped[float] = mapped_column(Float, default=0.0)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    turnover_rate: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    ma5: Mapped[float] = mapped_column(Float, default=0.0)
    ma10: Mapped[float] = mapped_column(Float, default=0.0)
    ma20: Mapped[float] = mapped_column(Float, default=0.0)
    ma60: Mapped[float] = mapped_column(Float, default=0.0)
    rsi_14: Mapped[float] = mapped_column(Float, default=0.0)
    macd: Mapped[float] = mapped_column(Float, default=0.0)
    atr_14: Mapped[float] = mapped_column(Float, default=0.0)
    volatility_20d: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_60d: Mapped[float] = mapped_column(Float, default=0.0)
    trend: Mapped[str] = mapped_column(String(20), default="")
    ma_alignment: Mapped[str] = mapped_column(String(20), default="")
    change_pct_5d: Mapped[float] = mapped_column(Float, default=0.0)
    change_pct_20d: Mapped[float] = mapped_column(Float, default=0.0)
    change_pct_60d: Mapped[float] = mapped_column(Float, default=0.0)
    volume_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    ma250: Mapped[float] = mapped_column(Float, default=0.0)
    kline_count: Mapped[int] = mapped_column(Integer, default=0)
    last_kline_date: Mapped[str] = mapped_column(String(10), default="")
    earnings_growth_3y: Mapped[float] = mapped_column(Float, default=0.0)
    eps: Mapped[float] = mapped_column(Float, default=0.0)
    bvps: Mapped[float] = mapped_column(Float, default=0.0)
    debt_to_equity: Mapped[float] = mapped_column(Float, default=0.0)
    net_income: Mapped[float] = mapped_column(Float, default=0.0)
    current_assets: Mapped[float] = mapped_column(Float, default=0.0)
    total_liabilities: Mapped[float] = mapped_column(Float, default=0.0)
    free_cash_flow: Mapped[float] = mapped_column(Float, default=0.0)
    revenue_growth_3y: Mapped[float] = mapped_column(Float, default=0.0)
    operating_margin: Mapped[float] = mapped_column(Float, default=0.0)
    current_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    cash_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    dividend_yield: Mapped[float] = mapped_column(Float, default=0.0)
    shares_outstanding: Mapped[float] = mapped_column(Float, default=0.0)
    cash_to_assets: Mapped[float] = mapped_column(Float, default=0.0)
    insider_holding_pct: Mapped[float] = mapped_column(Float, default=0.0)
    listing_days: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    notes_v2: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class KlineCache(Base):
    __tablename__ = "kline_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    open: Mapped[float] = mapped_column(Float, default=0.0)
    high: Mapped[float] = mapped_column(Float, default=0.0)
    low: Mapped[float] = mapped_column(Float, default=0.0)
    close: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    turnover_rate: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        Index("idx_kline_code_date", "stock_code", "trade_date", unique=True),
        Index("ix_kline_cache_stock_date", "stock_code", "trade_date"),
    )


class MarketSnapshot(Base):
    """Generic KV store for market snapshots (indices, north flow, sectors, etc.)

    Used by DatabaseBackedDataBus as a DB-first cache layer.
    Each row stores one snapshot type (e.g. 'indices', 'north_flow') as JSON.
    """

    __tablename__ = "market_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, unique=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    trade_date: Mapped[str] = mapped_column(String(10), default="")


class FundMetricHist(Base):
    """Fundamental metrics time series -- quarterly/annual"""

    __tablename__ = "fund_metric_hist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    report_period: Mapped[str] = mapped_column(String(10), nullable=False)
    report_type: Mapped[str] = mapped_column(String(10), default="quarter")
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    net_income: Mapped[float] = mapped_column(Float, default=0.0)
    net_income_parent: Mapped[float] = mapped_column(Float, default=0.0)
    gross_profit: Mapped[float] = mapped_column(Float, default=0.0)
    operating_income: Mapped[float] = mapped_column(Float, default=0.0)
    eps: Mapped[float] = mapped_column(Float, default=0.0)
    total_assets: Mapped[float] = mapped_column(Float, default=0.0)
    total_liabilities: Mapped[float] = mapped_column(Float, default=0.0)
    shareholders_equity: Mapped[float] = mapped_column(Float, default=0.0)
    current_assets: Mapped[float] = mapped_column(Float, default=0.0)
    current_liabilities: Mapped[float] = mapped_column(Float, default=0.0)
    cash_and_equivalents: Mapped[float] = mapped_column(Float, default=0.0)
    total_debt: Mapped[float] = mapped_column(Float, default=0.0)
    inventory: Mapped[float] = mapped_column(Float, default=0.0)
    accounts_receivable: Mapped[float] = mapped_column(Float, default=0.0)
    ocf_net: Mapped[float] = mapped_column(Float, default=0.0)
    capex: Mapped[float] = mapped_column(Float, default=0.0)
    fcf: Mapped[float] = mapped_column(Float, default=0.0)
    roe: Mapped[float] = mapped_column(Float, default=0.0)
    roa: Mapped[float] = mapped_column(Float, default=0.0)
    debt_to_equity: Mapped[float] = mapped_column(Float, default=0.0)
    current_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    gross_margin: Mapped[float] = mapped_column(Float, default=0.0)
    net_margin: Mapped[float] = mapped_column(Float, default=0.0)
    revenue_yoy: Mapped[float] = mapped_column(Float, default=0.0)
    net_income_yoy: Mapped[float] = mapped_column(Float, default=0.0)
    bvps: Mapped[float] = mapped_column(Float, default=0.0)
    dividend_per_share: Mapped[float] = mapped_column(Float, default=0.0)
    institution_holding_pct: Mapped[float] = mapped_column(Float, default=0.0)
    north_flow_hold: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_fmh_code_period", "stock_code", "report_period", unique=True),
        Index("idx_fmh_code_report", "stock_code", "report_type", "report_period"),
    )


class DragonTiger(Base):
    """Dragon-Tiger list -- limit-up board data"""

    __tablename__ = "dragon_tiger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), default="")
    limit_up_count: Mapped[int] = mapped_column(Integer, default=0)
    limit_type: Mapped[str] = mapped_column(String(10), default="")
    buy_dep1: Mapped[str] = mapped_column(String(100), default="")
    buy_amount1: Mapped[float] = mapped_column(Float, default=0.0)
    buy_dep2: Mapped[str] = mapped_column(String(100), default="")
    buy_amount2: Mapped[float] = mapped_column(Float, default=0.0)
    buy_dep3: Mapped[str] = mapped_column(String(100), default="")
    buy_amount3: Mapped[float] = mapped_column(Float, default=0.0)
    total_buy: Mapped[float] = mapped_column(Float, default=0.0)
    total_sell: Mapped[float] = mapped_column(Float, default=0.0)
    net_inflow: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_dt_date_code", "trade_date", "stock_code", unique=True),
        Index("idx_dt_buy1", "buy_dep1"),
    )
