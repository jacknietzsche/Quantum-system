"""超级工作流 — 统一状态模型"""

from typing import Any, TypedDict


class AShareSuperState(TypedDict):
    """超级工作流统一状态 — 融合所有Agent/Skill的完整上下文"""

    # ── 基础信息 ──
    date: str
    timestamp: str
    run_id: str

    # ── 第一层:全局数据总线 ──
    market_data: dict[str, Any]
    portfolio: list[dict[str, Any]]
    watchlist: list[dict[str, Any]]
    data_source: str
    prefetched_data: dict[str, Any]  # 数据收集器预取的每股数据

    # ── 第二层:25+ Skill并行分析 ──
    skill_outputs: dict[str, Any]
    skill_stats: dict[str, Any]

    # ── 第三层:AI对冲基金投委会 ──
    hedge_fund_decision: dict[str, Any]
    hedge_fund_signals: dict[str, Any]

    # ── 第四层:Fincept大师验证 ──
    fincept_verify: dict[str, Any]

    # ── 第五层:三层风险审计 ──
    risk_assessment: dict[str, Any]
    risk_pass: bool
    look_ahead_audit: dict[str, Any]

    # ── 第六层:组合管理 ──
    position_plan: dict[str, Any]
    rebalance_plan: dict[str, Any]

    # ── 第七层:输出 ──
    vote_results: dict[str, Any]
    recommendations: list[dict[str, Any]]
    report: str

    # ── 元信息 ──
    errors: list[str]
    logs: list[str]
    performance_metrics: dict[str, Any]
    degradation: dict[str, Any]
    aborted: bool
