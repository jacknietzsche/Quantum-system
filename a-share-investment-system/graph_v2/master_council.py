"""Master Council — 将项目内的 master-agent 和 skill 体系接入 v2 主图。

目标不是替代现有分析师/研究员，而是在进入核心辩论前提供:
1) 结构化大师观点 (master_views)
2) 可直接注入 prompt 的技能上下文 (skill_context)
3) 面向最终决策节点的综合摘要 (master_council_report)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe_num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_master_views(state: dict[str, Any]) -> list[dict[str, Any]]:
    from services.master_agents import get_master_agents

    stock_code = state.get("stock_code", "")
    if not stock_code:
        return []

    masters = get_master_agents()
    sample_financials = {
        "pe_ratio": _safe_num(state.get("pe_ratio")),
        "roe": _safe_num(state.get("roe")),
        "change_pct": _safe_num(state.get("change_pct")),
        "turnover_rate": _safe_num(state.get("turnover_rate")),
        "daily_volume_ratio": _safe_num(state.get("daily_volume_ratio")),
    }

    views: list[dict[str, Any]] = []
    for item in masters.analyze_all(stock_code, sample_financials):
        if not isinstance(item, dict):
            continue
        views.append(
            {
                "name": item.get("name", ""),
                "display_name": item.get("display_name", item.get("name", "")),
                "style": item.get("style", ""),
                "score": int(_safe_num(item.get("score"), 0)),
                "signal": item.get("signal", "neutral"),
                "reasoning": item.get("reasoning", ""),
            }
        )

    views.sort(key=lambda x: x.get("score", 0), reverse=True)
    return views


def build_skill_context(state: dict[str, Any]) -> str:
    from skills import register_all_skills, skill_registry

    stock_code = state.get("stock_code", "")
    register_all_skills()

    pieces: list[str] = []
    preferred = ["buffett", "munger", "taleb", "china_stock_research", "trading_agents_ashare"]
    for name in preferred:
        skill = skill_registry.get(name)
        if not skill:
            continue
        try:
            result = skill_registry.execute(
                name,
                {
                    "stock_code": stock_code,
                    "financials": {},
                    "market_data": {
                        "breadth": {"up": 0, "down": 0, "total": 0},
                        "indices": {},
                    },
                },
            )
        except Exception as exc:
            logger.debug("master view failed for %s: %s", name, exc)
            continue

        if not isinstance(result, dict):
            continue
        status = result.get("status", "ok")
        knowledge = result.get("knowledge") or result.get("orchestrator_knowledge") or ""
        if status == "ok" and knowledge:
            pieces.append(f"[{name}] {str(knowledge)[:800]}")

    return "\n\n".join(pieces[:5])


def _render_views_summary(views: list[dict[str, Any]]) -> str:
    if not views:
        return "无可用 Master Agent 视图。"

    bullish = [v for v in views if "bull" in v.get("signal", "") or "买" in v.get("signal", "")]
    bearish = [v for v in views if "bear" in v.get("signal", "") or "卖" in v.get("signal", "")]
    neutral = [v for v in views if v not in bullish and v not in bearish]

    top = views[:5]
    lines = [
        f"样本数: {len(views)}",
        f"多方观点: {len(bullish)} | 中性观点: {len(neutral)} | 空方观点: {len(bearish)}",
        "Top 5:",
    ]
    for v in top:
        lines.append(
            f"- {v['display_name']}({v['style']}): score={v['score']}, signal={v['signal']}"
        )
    return "\n".join(lines)


def _bucket_views(views: list[dict[str, Any]]):
    bullish = [v for v in views if "bull" in v.get("signal", "") or "买" in v.get("signal", "")]
    bearish = [v for v in views if "bear" in v.get("signal", "") or "卖" in v.get("signal", "")]
    neutral = [v for v in views if v not in bullish and v not in bearish]
    return bullish, bearish, neutral


def compute_master_factors(views: list[dict[str, Any]]) -> dict[str, float]:
    if not views:
        return {"master_weight_factor": 1.0, "master_position_factor": 1.0}

    bullish, bearish, _neutral = _bucket_views(views)
    n = len(views)
    avg_score = sum(v.get("score", 50) for v in views) / n
    direction_ratio = (len(bullish) - len(bearish)) / n

    weight_center = 1.0 + 0.30 * direction_ratio + 0.15 * ((avg_score - 50) / 50)
    weight_factor = max(0.70, min(1.30, weight_center))

    position_center = 1.0 + 0.25 * direction_ratio + 0.10 * ((avg_score - 50) / 50)
    position_factor = max(0.80, min(1.20, position_center))

    return {
        "master_weight_factor": round(weight_factor, 4),
        "master_position_factor": round(position_factor, 4),
    }


def build_master_council_report(views: list[dict[str, Any]], skill_context: str) -> str:
    factors = compute_master_factors(views)
    parts = [
        "## Master Council 摘要",
        _render_views_summary(views),
        f"**权重因子**: {factors['master_weight_factor']:.2f} | **仓位因子**: {factors['master_position_factor']:.2f}",
    ]
    if skill_context:
        parts.append("## Skill Context 摘要")
        parts.append(skill_context[:1800])
    return "\n\n".join(parts)


def create_master_council_node(config: dict[str, Any] | None = None):
    """返回一个 langgraph 节点函数, 将 master-agent/skill 信息写入主状态, 并产出量化权重因子。"""

    def _node(state: dict[str, Any]) -> dict[str, Any]:
        views = build_master_views(state)
        skill_context = build_skill_context(state)
        report = build_master_council_report(views, skill_context)
        factors = compute_master_factors(views)
        return {
            "master_views": views,
            "skill_context": skill_context,
            "master_council_report": report,
            "master_weight_factor": factors["master_weight_factor"],
            "master_position_factor": factors["master_position_factor"],
        }

    return _node
