"""5维市场环境感知服务 (移植自遗留版 a-share-investment-system/services/market_perception.py)

输入原始市场数据(breadth + indices),输出:
  - regime: BULL / NEUTRAL / BEAR / PANIC / OVERHEAT
  - dimension_scores: 5 维度独立评分 (-2 ~ +2)
  - adaptive_params: 自适应仓位参数
  - trading_phase: 当前交易时段

设计依据: 5 维度融合市场感知, 权重来自 QuantLLM IC 分析:
  - trend_position    0.25
  - trend_direction   0.25
  - volume_confirm    0.15
  - volatility        0.15
  - price_momentum    0.20
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


DIMENSION_WEIGHTS: dict[str, float] = {
    "trend_position": 0.25,
    "trend_direction": 0.25,
    "volume_confirm": 0.15,
    "volatility": 0.15,
    "price_momentum": 0.20,
}


def _score_dimensions(breadth: dict, indices: dict) -> dict[str, float]:
    """5 维度独立评分 (范围 -2 ~ +2)。"""
    up = breadth.get("up", 0)
    down = breadth.get("down", 0)
    total = breadth.get("total", 1)
    limit_down = breadth.get("limit_down", 0)
    limit_up = breadth.get("limit_up", 0)

    if total > 0:
        up_ratio = up / total
        if up_ratio > 0.7:
            d1_score = min(2.0, (up_ratio - 0.5) * 5)
        elif up_ratio < 0.3:
            d1_score = max(-2.0, (up_ratio - 0.5) * 5)
        else:
            d1_score = (up_ratio - 0.5) * 4
    else:
        d1_score = 0.0

    if total > 0:
        imbalance = (up - down) / total
        d2_score = max(-2.0, min(2.0, imbalance * 3))
    else:
        d2_score = 0.0

    if limit_up + limit_down > 0:
        d3_score = max(-2.0, min(2.0, (limit_up - limit_down) / max(total, 1) * 20))
    else:
        d3_score = 0.0

    if total > 0:
        limit_down_ratio = limit_down / total
        limit_up_ratio = limit_up / total
        if limit_down_ratio > 0.10:
            d4_score = -2.0
        elif limit_down_ratio > 0.05:
            d4_score = -1.5
        elif limit_down_ratio > 0.02:
            d4_score = -0.8
        elif limit_up_ratio > 0.15:
            d4_score = 2.0
        elif limit_up_ratio > 0.10:
            d4_score = 1.0
        elif limit_up_ratio > 0.05:
            d4_score = 0.5
        else:
            d4_score = 0.0
    else:
        d4_score = 0.0

    if total > 0:
        up_ratio = up / total
        if up_ratio > 0.85:
            d5_score = 2.0
        elif up_ratio > 0.75:
            d5_score = 1.5
        elif up_ratio > 0.65:
            d5_score = 1.0
        elif up_ratio < 0.15:
            d5_score = -2.0
        elif up_ratio < 0.25:
            d5_score = -1.5
        elif up_ratio < 0.35:
            d5_score = -1.0
        else:
            d5_score = 0.0
    else:
        d5_score = 0.0

    return {
        "trend_position": round(d1_score, 1),
        "trend_direction": round(d2_score, 1),
        "volume_confirm": round(d3_score, 1),
        "volatility": round(d4_score, 1),
        "price_momentum": round(d5_score, 1),
    }


def _classify_regime(total: float, breadth: dict) -> str:
    """根据总分和市场广度判定市场环境。"""
    limit_down = breadth.get("limit_down", 0)
    limit_up = breadth.get("limit_up", 0)
    total_stocks = breadth.get("total", 1)

    if limit_down > 50 and total < -1.0:
        return "PANIC"
    if limit_up > 150 and total_stocks > 0 and limit_up / total_stocks > 0.03:
        return "OVERHEAT"

    if total >= 1.0:
        return "BULL"
    if total <= -1.0:
        return "BEAR"
    return "NEUTRAL"


def _adaptive_params(regime: str) -> dict[str, Any]:
    """根据 regime 返回仓位/选股阈值。"""
    params = {
        "BULL": {
            "target_position_pct": 0.95,
            "max_holdings": 10,
            "selection_threshold": "buy+strong_buy",
        },
        "NEUTRAL": {
            "target_position_pct": 0.50,
            "max_holdings": 5,
            "selection_threshold": "buy+strong_buy",
        },
        "BEAR": {
            "target_position_pct": 0.30,
            "max_holdings": 3,
            "selection_threshold": "strong_buy_only",
        },
        "PANIC": {
            "target_position_pct": 0.10,
            "max_holdings": 1,
            "selection_threshold": "strong_buy_only",
        },
        "OVERHEAT": {
            "target_position_pct": 0.70,
            "max_holdings": 8,
            "selection_threshold": "buy+strong_buy",
        },
    }
    return params.get(regime, params["NEUTRAL"])


def _detect_trading_phase(now: datetime | None = None) -> str:
    """Detect current trading phase.

    Returns one of: pre_market, intraday_morning, lunch_break,
    intraday_afternoon, post_market, holiday.
    """
    now = now or datetime.now()
    hour = now.hour + now.minute / 60.0
    weekday = now.weekday()
    if weekday >= 5:
        return "holiday"
    if hour < 9.5:
        return "pre_market"
    if 9.5 <= hour <= 11.5:
        return "intraday_morning"
    if 11.5 < hour < 13.0:
        return "lunch_break"
    if 13.0 <= hour <= 15.0:
        return "intraday_afternoon"
    return "post_market"


def perceive(market_data: dict[str, Any]) -> dict[str, Any]:
    """5 维度融合市场环境感知 (纯函数版, 替代遗留版 BaseService 形式)。

    Args:
        market_data: {"breadth": {...}, "indices": {...}}

    Returns:
        {
          "regime": str, "total_score": float,
          "dimension_scores": dict, "adaptive_params": dict,
          "trading_phase": str,
        }
    """
    try:
        breadth = market_data.get("breadth", {})
        indices = market_data.get("indices", {})
        scores = _score_dimensions(breadth, indices)
        total = sum(s * DIMENSION_WEIGHTS[k] for k, s in scores.items())
        regime = _classify_regime(total, breadth)
        adaptive = _adaptive_params(regime)
        phase = _detect_trading_phase()
        return {
            "regime": regime,
            "total_score": round(total, 2),
            "dimension_scores": scores,
            "adaptive_params": adaptive,
            "trading_phase": phase,
        }
    except Exception as e:
        logger.error("MarketPerception.perceive failed: %s", e)
        return {
            "regime": "NEUTRAL",
            "total_score": 0.0,
            "dimension_scores": dict.fromkeys(DIMENSION_WEIGHTS, 0.0),
            "adaptive_params": _adaptive_params("NEUTRAL"),
            "trading_phase": _detect_trading_phase(),
            "error": str(e),
        }


# ── 兼容旧 API: get_market_overview / get_market_state ──


def get_market_overview() -> dict[str, Any]:
    """获取市场概览 (通过 DatabaseFirstDataBus, 兼容旧 API)。"""
    try:
        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        return bus.get_market_overview()
    except Exception as e:
        logger.warning("get_market_overview fallback: %s", e)
        return {"market_state": "NEUTRAL", "indices": {}, "advance_count": 0, "decline_count": 0}


def get_market_state() -> str:
    """获取当前市场状态: BULL/NEUTRAL/BEAR/PANIC。"""
    overview = get_market_overview()
    state = overview.get("market_state", "NEUTRAL")
    return str(state) if state is not None else "NEUTRAL"


def is_trading_day(date: str | None = None) -> bool:
    """判断是否为 A 股交易日 (简化版: 仅排除周末)。"""
    target = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    return target.weekday() < 5
