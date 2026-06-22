"""组合管理（仓位优化）。

设计依据: S08 §8.6, experiments exp9.2/exp9.3。
行业分散 + 仓位约束 + 再平衡。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def optimize_positions(
    candidates: list[dict],
    total_capital: float,
    max_single_pct: float = 0.15,
    max_industry_pct: float = 0.30,
    market_state: str = "NEUTRAL",
) -> list[dict]:
    """
    仓位优化算法:
    1. 按评分排序
    2. 逐个分配仓位
    3. 检查单只/行业/总仓位上限
    """
    market_caps = {
        "PANIC": 0.10,
        "BEAR": 0.30,
        "NEUTRAL": 0.60,
        "BULL": 0.80,
        "OVERHEAT": 0.50,
    }
    max_total_pct = market_caps.get(market_state, 0.60)

    sorted_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

    result = []
    used_pct = 0.0
    industry_used = {}

    for stock in sorted_candidates:
        if len(result) >= 10:
            break

        industry = stock.get("industry", "未知")
        base_pct = min(max_single_pct, stock.get("score", 50) / 100 * 0.2)
        actual_pct = min(base_pct, max_single_pct)

        industry_pct = industry_used.get(industry, 0) + actual_pct
        if industry_pct > max_industry_pct:
            actual_pct = max(0, max_industry_pct - industry_used.get(industry, 0))

        if used_pct + actual_pct > max_total_pct:
            actual_pct = max(0, max_total_pct - used_pct)

        if actual_pct > 0.01:
            result.append(
                {
                    **stock,
                    "position_pct": round(actual_pct * 100, 1),
                    "position_amount": round(total_capital * actual_pct, 0),
                }
            )
            used_pct += actual_pct
            industry_used[industry] = industry_used.get(industry, 0) + actual_pct

    return result


def check_industry_constraint(portfolio: list[dict], max_per_industry: int = 3) -> list[str]:
    """检查行业集中度约束。"""
    industry_count = {}
    violations = []
    for stock in portfolio:
        industry = stock.get("industry", "未知")
        industry_count[industry] = industry_count.get(industry, 0) + 1
        if industry_count[industry] > max_per_industry:
            violations.append(f"{stock.get('code', 'N/A')} 超出行业上限: {industry}")
    return violations


def compute_rebalance(current: list[dict], target: list[dict]) -> list[dict]:
    """计算再平衡操作。"""
    operations = []
    current_codes = {s["code"]: s for s in current}
    target_codes = {s["code"]: s for s in target}

    for code, stock in current_codes.items():
        if code not in target_codes:
            operations.append({"action": "SELL", "code": code, "name": stock.get("name", "")})

    for code, stock in target_codes.items():
        if code not in current_codes:
            operations.append(
                {
                    "action": "BUY",
                    "code": code,
                    "name": stock.get("name", ""),
                    "target_pct": stock.get("position_pct", 0),
                }
            )

    for code in set(current_codes.keys()) & set(target_codes.keys()):
        diff = target_codes[code].get("position_pct", 0) - current_codes[code].get(
            "position_pct", 0
        )
        if abs(diff) > 2:
            operations.append({"action": "ADJUST", "code": code, "diff": round(diff, 1)})

    return operations
