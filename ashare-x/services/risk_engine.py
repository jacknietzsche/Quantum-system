"""风险引擎（三层风险体系）。

设计依据: S08 §8.1-8.3。
L1市场风险 + L2个股风险 + L3组合风险。
"""

from __future__ import annotations

import logging

from tools.market_state import detect_market_state, get_position_cap

logger = logging.getLogger(__name__)


def assess_market_risk(indices_data: dict) -> dict:
    """L1: 市场风险评估。"""
    state = detect_market_state(indices_data)
    cap = get_position_cap(state)
    return {"market_state": state, "position_cap": cap}


def assess_stock_risk(stock_data: dict) -> dict:
    """L2: 个股风险评估。"""
    volatility = stock_data.get("volatility", 0.3)
    volume = stock_data.get("volume", 0)
    avg_volume = stock_data.get("avg_volume", volume)

    risk_level = "low"
    if volatility > 0.4:
        risk_level = "high"
    elif volatility > 0.25:
        risk_level = "medium"

    liquidity_ok = volume > avg_volume * 0.5 if avg_volume else True

    return {
        "risk_level": risk_level,
        "volatility": volatility,
        "liquidity_ok": liquidity_ok,
    }


def assess_portfolio_risk(portfolio: list[dict]) -> dict:
    """L3: 组合风险评估。"""
    industry_exposure: dict[str, float] = {}
    for stock in portfolio:
        ind = stock.get("industry", "未知")
        pct = stock.get("position_pct", 0)
        industry_exposure[ind] = industry_exposure.get(ind, 0) + pct

    max_exposure = max(industry_exposure.values()) if industry_exposure else 0
    concentration_risk = max_exposure > 30

    return {
        "industry_exposure": industry_exposure,
        "max_exposure_pct": max_exposure,
        "concentration_risk": concentration_risk,
    }
