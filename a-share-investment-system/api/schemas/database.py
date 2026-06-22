"""Pydantic 请求/响应模型 — 数据库管理 API"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── StockInfo ──


class StockInfoOut(BaseModel):
    """StockInfo 响应模型"""

    stock_code: str
    stock_name: str
    industry: str = ""
    latest_price: float = 0
    change_pct: float = 0
    pe_ratio: float = 0
    pb_ratio: float = 0
    roe: float = 0
    total_market_cap: float = 0
    turnover_rate: float = 0
    trend: str = ""
    ma5: float = 0
    ma10: float = 0
    ma20: float = 0
    rsi_14: float = 0
    volatility_20d: float = 0
    updated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StockInfoListOut(BaseModel):
    """StockInfo 列表响应"""

    total: int
    page: int
    limit: int
    stocks: list[dict[str, Any]]


class AddStockIn(BaseModel):
    """添加股票请求"""

    stock_code: str = Field(..., min_length=6, max_length=6, description="6位股票代码")
    stock_name: str = ""
    price: float = 0
    pe: float = 0
    pb: float = 0
    roe: float = 0
    industry: str = ""


class EditStockIn(BaseModel):
    """编辑股票请求"""

    stock_name: str | None = None
    industry: str | None = None
    trend: str | None = None
    latest_price: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    roe: float | None = None


class OkResponse(BaseModel):
    """通用操作响应"""

    ok: bool
    error: str = ""


# ── Refresh ──


class RefreshIn(BaseModel):
    """刷新数据请求"""

    mode: str = Field(default="hot", pattern="^(hot|full)$", description="hot=热榜100, full=全市场")
    codes: list[str] = []
    max_stocks: int = Field(default=10000, ge=100, le=50000)


class RefreshResultOut(BaseModel):
    """刷新结果"""

    ok: bool
    result: dict[str, Any] | None = None
    error: str = ""


# ── Stats ──


class SourceStatusOut(BaseModel):
    """数据源状态"""

    sources: dict[str, Any]
    chain: str


class DbStatsOut(BaseModel):
    """数据库统计"""

    stock_count: int
    kline_count: int
    last_kline_date: str | None = None
    snapshot_count: int
    latest_update: str
    data_sources: list[str]
    source_chain: str
    source_status: dict[str, Any]
    needs_refresh: bool
    refresh_hint: str
    db_size_mb: float = 0.0


# ── Kline ──


class KlineItem(BaseModel):
    """K线数据项"""

    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float


class KlineOut(BaseModel):
    """K线响应"""

    code: str
    count: int
    klines: list[KlineItem]


# ── Hot Stocks ──


class HotStockItem(BaseModel):
    """热榜股票项"""

    code: str
    name: str
    price: float = 0
    change_pct: float = 0
    turnover_rate: float = 0
    market_cap: float = 0


class HotStocksOut(BaseModel):
    """热榜响应"""

    stocks: list[HotStockItem]
    count: int
    source: str = ""
    missing_data: int = 0
    hint: str = ""


# ── Industry Distribution ──


class IndustryItem(BaseModel):
    """行业分布项"""

    name: str
    count: int
    avg_pe: float = 0
    avg_roe: float = 0
    total_market_cap_yi: float = 0


class IndustryDistOut(BaseModel):
    """行业分布响应"""

    industries: list[IndustryItem]
    total_with_industry: int = 0
    total_no_industry: int = 0


# ── Snapshots ──


class SnapshotItem(BaseModel):
    """快照项"""

    type: str
    updated: str


class SnapshotsOut(BaseModel):
    """快照列表响应"""

    count: int
    snapshots: list[SnapshotItem]
