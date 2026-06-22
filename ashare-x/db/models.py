"""ORM模型定义（15张表）。

设计依据: S05 §5.8, 现有系统 shared/models.py。
直接复用现有系统的表结构，精简后保留核心表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class KlineDaily(Base):
    """日K线数据（永久存储）"""

    __tablename__ = "kline_daily"

    stock_code = Column(String(20), primary_key=True)
    trade_date = Column(String(10), primary_key=True)  # YYYY-MM-DD
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    change_pct = Column(Float)
    turnover_rate = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class StockInfo(Base):
    """股票基础信息 + 行情快照"""

    __tablename__ = "stock_info"

    stock_code = Column(String(20), primary_key=True)
    stock_name = Column(String(50))
    category = Column(String(20))
    industry = Column(String(50))
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    roe = Column(Float)
    latest_price = Column(Float)
    change_pct = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    turnover_rate = Column(Float)
    ma5 = Column(Float)
    ma20 = Column(Float)
    ma60 = Column(Float)
    rsi_14 = Column(Float)
    macd = Column(Float)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MarketSnapshot(Base):
    """市场快照（指数/北向/板块）"""

    __tablename__ = "market_snapshot"

    snapshot_type = Column(String(50), primary_key=True)  # indices/north_flow/sectors
    trade_date = Column(String(10))
    data_json = Column(Text)  # JSON存储
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class FundMetricHist(Base):
    """财务指标时序（季报/年报）"""

    __tablename__ = "fund_metric_hist"

    stock_code = Column(String(20), primary_key=True)
    report_period = Column(String(10), primary_key=True)  # YYYY-Q1/Q2/Q3/Q4/YYYY
    revenue = Column(Float)
    net_income = Column(Float)
    gross_profit = Column(Float)
    roe = Column(Float)
    roa = Column(Float)
    debt_to_equity = Column(Float)
    current_ratio = Column(Float)
    gross_margin = Column(Float)
    net_margin = Column(Float)
    revenue_yoy = Column(Float)
    net_income_yoy = Column(Float)
    bvps = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class DragonTiger(Base):
    """龙虎榜数据"""

    __tablename__ = "dragon_tiger"

    trade_date = Column(String(10), primary_key=True)
    stock_code = Column(String(20), primary_key=True)
    limit_up_count = Column(Integer)
    limit_type = Column(String(20))
    buy_dep1 = Column(String(50))
    buy_amount1 = Column(Float)
    total_buy = Column(Float)
    total_sell = Column(Float)
    net_inflow = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class Portfolio(Base):
    """持仓"""

    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(50))
    buy_price = Column(Float)
    quantity = Column(Integer)
    current_price = Column(Float)
    status = Column(String(20), default="HOLDING")  # HOLDING/SOLD
    portfolio_type = Column(String(20), default="paper")  # paper/real
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TradeRecords(Base):
    """交易记录"""

    __tablename__ = "trade_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False)
    trade_type = Column(String(10))  # BUY/SELL
    price = Column(Float)
    quantity = Column(Integer)
    amount = Column(Float)
    commission = Column(Float)
    tax = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class Reports(Base):
    """分析报告"""

    __tablename__ = "reports"

    id = Column(String(50), primary_key=True)
    ticker = Column(String(20), nullable=False)
    stock_name = Column(String(50))
    date = Column(String(10))
    action = Column(String(10))  # Buy/Sell/Hold
    confidence = Column(Float)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    position_pct = Column(Float)
    token_usage = Column(Integer)
    execution_time_seconds = Column(Float)
    agents_executed = Column(Text)  # JSON list
    created_at = Column(DateTime, default=datetime.now)


class DecisionLog(Base):
    """决策日志"""

    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    date = Column(String(10))
    action = Column(String(10))
    confidence = Column(Float)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    thesis = Column(Text)
    reflection = Column(Text)
    source_agents = Column(Text)  # JSON list
    outcome_profit = Column(Float)
    outcome_return_pct = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class MigrationVersion(Base):
    """迁移版本追踪"""

    __tablename__ = "_migration_version"

    version = Column(Integer, primary_key=True)
    description = Column(String(200))
    applied_at = Column(DateTime, default=datetime.now)
