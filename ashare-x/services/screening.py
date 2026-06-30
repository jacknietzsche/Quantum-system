"""选股服务（评分 + 排名）。

设计依据: S08 §8.6, experiments exp9.1。
多因子评分 + 硬性过滤。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get(stock: dict, key: str, default: float) -> float:
    """获取字段值，显式处理 None。"""
    val = stock.get(key, default)
    return default if val is None else val


def compute_stock_score(stock: dict, style: str = "balanced") -> float:
    """
    多因子评分公式（0-100分）:
    - 价值因子 (25%): PE/PB/股息率
    - 成长因子 (25%): 营收增速/利润增速
    - 动量因子 (25%): 20日涨幅/RSI
    - 质量因子 (25%): ROE/现金流
    """
    weights = {
        "balanced": {"value": 0.25, "growth": 0.25, "momentum": 0.25, "quality": 0.25},
        "value": {"value": 0.40, "growth": 0.20, "momentum": 0.20, "quality": 0.20},
        "growth": {"value": 0.20, "growth": 0.40, "momentum": 0.20, "quality": 0.20},
        "momentum": {"value": 0.20, "growth": 0.20, "momentum": 0.40, "quality": 0.20},
    }
    w = weights.get(style, weights["balanced"])

    # 价值因子
    pe = _get(stock, "pe_ratio", 50)
    pb = _get(stock, "pb_ratio", 5)
    div = _get(stock, "dividend_yield", 0) * 100
    value_score = max(
        0,
        min(
            100,
            (100 - (pe - 10) * 3) * 0.4 + (100 - (pb - 0.5) * 20) * 0.3 + div * 20 * 0.3,
        ),
    )

    # 成长因子
    rev_growth = _get(stock, "revenue_growth", 0) * 100
    profit_growth = _get(stock, "profit_growth", 0) * 100
    growth_score = max(0, min(100, (rev_growth + profit_growth) / 2 + 50))

    # 动量因子
    change_20d = _get(stock, "change_pct_20d", 0) * 100
    momentum_price = max(0, min(100, 100 - abs(change_20d - 10) * 5))
    rsi = _get(stock, "rsi_14", 50)
    momentum_rsi = max(0, min(100, 100 - abs(rsi - 55) * 3))
    momentum_score = momentum_price * 0.5 + momentum_rsi * 0.5

    # 质量因子
    roe = _get(stock, "roe", 0) * 100
    quality_roe = max(0, min(100, roe * 3))
    quality_score = quality_roe

    # 保存分项得分供前端展示
    stock["value_score"] = value_score
    stock["growth_score"] = growth_score
    stock["momentum_score"] = momentum_score
    stock["quality_score"] = quality_score

    # 加权总分
    total = (
        value_score * w["value"]
        + growth_score * w["growth"]
        + momentum_score * w["momentum"]
        + quality_score * w["quality"]
    )
    return round(total, 1)


def hard_filter(stock: dict, config: dict | None = None) -> bool:
    """硬性过滤条件。"""
    config = config or {}
    if config.get("exclude_st", True) and stock.get("is_st", False):
        return False
    if stock.get("listing_days", 999) < config.get("exclude_new_days", 60):
        return False
    if stock.get("amount", 0) < config.get("min_turnover", 5_000):
        return False
    return not stock.get("is_suspended", False)


def rank_stocks(stocks: list[dict], top_n: int = 20, style: str = "balanced") -> list[dict]:
    """评分 + 排序 + 返回Top N。"""
    filtered = [s for s in stocks if hard_filter(s)]
    for stock in filtered:
        stock["score"] = compute_stock_score(stock, style)
    ranked = sorted(filtered, key=lambda x: x["score"], reverse=True)
    return ranked[:top_n]
