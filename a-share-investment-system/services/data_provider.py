"""统一数据提供者协议 - 日频数据源抽象层"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class DailyBar:
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float
    amount: float = 0.0
    pct_chg: float = 0.0


@dataclass
class FundamentalSnapshot:
    pe: float = 0.0
    pb: float = 0.0
    roe: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    debt_to_equity: float = 0.0
    revenue_growth: float = 0.0
    earnings_growth: float = 0.0


@dataclass
class DragonTigerEntry:
    trade_date: str
    stock_code: str
    stock_name: str = ""
    limit_up_count: int = 0
    buy_total: float = 0.0
    sell_total: float = 0.0
    net_inflow: float = 0.0
    top_departments: list[str] = field(default_factory=list)


@runtime_checkable
class DataProvider(Protocol):
    def get_daily_klines(self, code: str, days: int = 90) -> list[DailyBar]: ...
    def get_fundamentals(self, code: str) -> FundamentalSnapshot: ...
    def get_dragon_tiger(self, date: str | None = None) -> list[DragonTigerEntry]: ...
    def get_north_flow(self, code: str) -> float | None: ...
    def is_available(self) -> bool: ...
