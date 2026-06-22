"""QuantAgent 数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketDiagnosis:
    """市场诊断 (复用 screening.market_perception)"""

    state: str = "SHOCK"
    confidence: float = 0.5
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "trend": 0.25,
            "capital": 0.25,
            "fundamental": 0.25,
            "defensive": 0.25,
        }
    )
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyPlan:
    """AI自主制定的策略计划"""

    style: str = "hybrid"  # hybrid / defensive / momentum / limit_up
    factor_weights: dict[str, float] = field(default_factory=dict)
    max_positions: int = 8
    risk_budget: float = 0.15
    reasoning: str = ""
    screening_filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class StockPick:
    """AI推荐的一只股票"""

    rank: int = 0
    stock_code: str = ""
    stock_name: str = ""
    score: float = 0.0
    weight: float = 0.0  # 建议仓位比例
    reason: str = ""  # AI推荐理由
    stop_loss: float = 0.0  # 止损价%
    take_profit: float = 0.0  # 止盈价%
    risk: str = ""  # AI识别的风险
    signal: str = "观望"
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DecisionReport:
    """最终决策报告"""

    date: str = ""
    picks: list[StockPick] = field(default_factory=list)
    portfolio_summary: str = ""
    risk_warnings: list[str] = field(default_factory=list)
    state_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThoughtStep:
    """AI思考过程的一步"""

    phase: str = ""  # perceive / judge / act / decide / reflect
    title: str = ""
    content: str = ""  # AI原始输出
    summary: str = ""  # 前端展示用摘要
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class Reflection:
    """AI复盘反思"""

    date: str = ""
    summary: str = ""
    insights: list[str] = field(default_factory=list)
    mistakes: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)


@dataclass
class QuantAgentState:
    """QuantAgent 运行状态 (供 API 和 Pinia store 使用)"""

    status: str = "idle"  # idle / thinking / done / error
    current_phase: str | None = None
    diagnosis: MarketDiagnosis | None = None
    thoughts: list[ThoughtStep] = field(default_factory=list)
    final_picks: list[StockPick] = field(default_factory=list)
    decision_report: str = ""
    error: str = ""
