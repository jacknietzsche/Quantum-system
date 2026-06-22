"""Pydantic 模型 — 自选股/报告/任务/分析/系统 API"""

from typing import Any

from pydantic import BaseModel

# === Favorites (watchlist) ===


class FavoriteItem(BaseModel):
    """自选股条目"""

    stock_code: str
    stock_name: str
    created_at: str = ""
    current_price: float = 0.0
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    industry: str = ""
    trend: str = ""
    change_pct: float = 0.0


class FavoriteListOut(BaseModel):
    """自选股列表响应"""

    data: list[FavoriteItem] = []
    error: str = ""


class AddFavoriteIn(BaseModel):
    """添加自选股请求"""

    stock_code: str = ""
    stock_name: str = ""


class FavoriteCheckOut(BaseModel):
    """自选股检查响应"""

    is_favorite: bool = False
    stock_code: str = ""
    error: str = ""


# === Tasks ===


class TaskItem(BaseModel):
    """任务条目"""

    id: str = ""
    task_id: str = ""
    stock_code: str = ""
    stock_name: str = ""
    status: str = ""
    signal: str = ""
    confidence: float = 0.0
    progress: float = 0.0
    error: str = ""
    created_at: str = ""
    finish_time: str = ""


class TaskListOut(BaseModel):
    """任务列表响应"""

    tasks: list[TaskItem] = []
    total: int = 0
    error: str = ""


class TaskDetailOut(BaseModel):
    """任务详情响应"""

    id: str = ""
    task_id: str = ""
    stock_code: str = ""
    stock_name: str = ""
    status: str = ""
    signal: str = ""
    confidence: float = 0.0
    progress: float = 0.0
    result: Any = None
    error: str = ""
    created_at: str = ""
    finish_time: str = ""


class TaskQueueOut(BaseModel):
    """队列状态响应"""

    running: int = 0
    queued: int = 0
    total: int = 0


# === Reports ===


class ReportItem(BaseModel):
    """报告条目"""

    id: str = ""
    stock_code: str = ""
    stock_name: str = ""
    analysis_date: str = ""
    signal: str = ""
    confidence: float = 0.0


class ReportListOut(BaseModel):
    """报告列表响应"""

    reports: list[ReportItem] = []
    total: int = 0
    error: str = ""


class ReportDetailOut(BaseModel):
    """报告详情响应"""

    id: str = ""
    stock_code: str = ""
    stock_name: str = ""
    analysis_date: str = ""
    signal: str = ""
    confidence: float = 0.0
    content: str = ""
    result: Any = None
    error: str = ""


class LatestBySymbolsIn(BaseModel):
    """批量查询请求"""

    symbols: list[str] = []


class LatestBySymbolsOut(BaseModel):
    """批量查询响应"""

    reports: list[ReportItem] = []
    error: str = ""


# === Analysis ===


class AnalystScoreOut(BaseModel):
    """分析师评分"""

    analyst: str = ""
    stock_code: str = ""
    score: float = 0
    signal: str = "neutral"
    details: dict[str, Any] = {}


class ValuationOut(BaseModel):
    """估值结果"""

    buffett: AnalystScoreOut | None = None
    graham: AnalystScoreOut | None = None
    lynch: AnalystScoreOut | None = None


class AnalysisOut(BaseModel):
    """分析响应"""

    stock_code: str = ""
    stock_name: str = ""
    valuation: ValuationOut | None = None
    factors: Any = None
    signal: str = "neutral"
    error: str = ""


# === System ===


class DatabaseHealthOut(BaseModel):
    """数据库健康状态"""

    total_stocks: int = 0
    kline_records: int = 0
    disk_mb: float = 0.0
    healthy: bool = False
    completeness_pct: float = 0.0


class SourceDetailOut(BaseModel):
    """数据源详细信息"""

    name: str = ""
    state: str = ""
    failures: int = 0
    total_calls: int = 0
    successes: int = 0
    available: bool = False
    cooldown_remaining: float = 0.0


class LatencyDetailOut(BaseModel):
    """延迟测试结果"""

    ok: bool = False
    latency_ms: int = 0
    error: str | None = None


class SourceHealthOut(BaseModel):
    """数据源健康状态"""

    total_sources: int = 0
    working_sources: int = 0
    circuit_breakers: dict[str, SourceDetailOut] = {}
    latency: dict[str, LatencyDetailOut] = {}
    http_pools: dict[str, dict] = {}


class SystemStatusOut(BaseModel):
    """系统状态响应"""

    status: str = ""
    version: str = ""
    database: DatabaseHealthOut | None = None
    data_sources: dict[str, SourceDetailOut] = {}
    error: str = ""


# === Common ===


class OkResponse(BaseModel):
    """通用操作响应"""

    ok: bool = True
    error: str = ""
    data: dict | None = None


class ErrorResponse(BaseModel):
    """错误响应"""

    error: str = ""
