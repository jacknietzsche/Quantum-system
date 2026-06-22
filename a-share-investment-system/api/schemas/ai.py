"""Pydantic 请求/响应模型 — AI 认知 API"""

from pydantic import BaseModel


class MarketStateOut(BaseModel):
    """AI市场诊断"""

    summary: str = "加载市场认知..."
    confidence: float = 0.0
    regime: str = "NEUTRAL"
    strategy_weights: dict[str, float] = {}
    risk_level: str = "medium"


class AgentHealthEntry(BaseModel):
    """Agent健康度条目"""

    name: str
    display_name: str = ""
    accuracy_7d: float = 0.0
    accuracy_30d: float = 0.0
    accuracy_all: float = 0.0
    total_picks: int = 0
    correct_picks: int = 0
    avg_return: float = 0.0


class AgentHealthOut(BaseModel):
    """Agent健康度列表"""

    agents: list[AgentHealthEntry] = []


class MemoryDayOut(BaseModel):
    """复盘日历单日条目"""

    trade_date: str
    regime: str = ""
    picks_count: int = 0
    correct_count: int = 0
    avg_return: float = 0.0
    market_return: float = 0.0
    reflection: str = ""


class MemoryCalendarOut(BaseModel):
    """复盘日历"""

    days: list[MemoryDayOut] = []


class SimilarDayOut(BaseModel):
    """相似市场历史条目"""

    trade_date: str
    similarity: float = 0.0
    regime: str = ""
    strategy: str = ""
    result: float = 0.0


class SimilarMarketsOut(BaseModel):
    """相似市场检索结果"""

    similar_days: list[SimilarDayOut] = []
