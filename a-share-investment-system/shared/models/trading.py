"""Trading domain models — OrderStatus, OrderDirection, Order, Trade"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.models._base import Base


class OrderStatus(enum.Enum):
    PENDING = "未执行"
    FILLED = "已成交"
    CANCELLED = "已撤销"
    PARTIAL = "部分成交"


class OrderDirection(enum.Enum):
    BUY = "买入"
    SELL = "卖出"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[OrderDirection] = mapped_column(Enum(OrderDirection), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_type: Mapped[str] = mapped_column(String(20), default="市价单")
    limit_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING, index=True
    )
    signal_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    signal_reason: Mapped[str] = mapped_column(Text, default="")
    target_date: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    portfolio_type: Mapped[str] = mapped_column(String(20), default="value", index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)
    filled_price: Mapped[float] = mapped_column(Float, default=0.0)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_cost: Mapped[float] = mapped_column(Float, default=0.0)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[OrderDirection] = mapped_column(Enum(OrderDirection), nullable=False)
    execute_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_cost: Mapped[float] = mapped_column(Float, default=0.0)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    portfolio_type: Mapped[str] = mapped_column(String(20), default="value", index=True)
