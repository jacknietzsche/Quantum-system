"""Portfolio domain models — Portfolio, TradeRecord, DailyReport, Watchlist, DailyNAV"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.models._base import Base


class TradeStatus(enum.Enum):
    HOLDING = "持有"
    SOLD = "卖出"


class TradeType(enum.Enum):
    BUY = "买入"
    SELL = "卖出"


class RiskLevel(enum.Enum):
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    EXTREME = "极高风险"


class Portfolio(Base):
    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False)
    buy_date: Mapped[str] = mapped_column(String(10), nullable=False)
    buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[TradeStatus] = mapped_column(Enum(TradeStatus), default=TradeStatus.HOLDING)
    sell_date: Mapped[str | None] = mapped_column(String(10))
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_reason: Mapped[str] = mapped_column(Text, default="")
    buy_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    portfolio_type: Mapped[str] = mapped_column(String(20), default="value", index=True)

    @property
    def cost_value(self):
        return self.buy_price * self.quantity

    @property
    def current_value(self):
        if self.status == TradeStatus.HOLDING:
            return (self.current_price or 0) * self.quantity
        return (self.sell_price or 0) * self.quantity

    @property
    def profit_loss(self):
        if self.status == TradeStatus.HOLDING:
            return ((self.current_price or 0) - self.buy_price) * self.quantity
        return ((self.sell_price or 0) - self.buy_price) * self.quantity

    @property
    def profit_loss_pct(self):
        return (self.profit_loss / self.cost_value * 100) if self.cost_value > 0 else 0


class TradeRecord(Base):
    __tablename__ = "trade_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_type: Mapped[TradeType] = mapped_column(Enum(TradeType), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    portfolio_type: Mapped[str] = mapped_column(String(20), default="value", index=True)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    market_summary: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[str] = mapped_column(Text, default="")
    portfolio_snapshot: Mapped[str] = mapped_column(Text, default="")
    total_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.MEDIUM)
    report_file: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False)
    add_reason: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="候选")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DailyNAV(Base):
    __tablename__ = "daily_nav"
    __table_args__ = (Index("idx_nav_date_type", "date", "portfolio_type", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    total_asset: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    stock_value: Mapped[float] = mapped_column(Float, default=0.0)
    daily_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cumulative_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    position_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_quadrant: Mapped[str] = mapped_column(String(5), default="")
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    portfolio_type: Mapped[str] = mapped_column(String(20), default="value", index=True)
