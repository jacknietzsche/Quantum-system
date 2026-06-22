"""6 master-quant analyzers - pure-algorithm edition (ported from legacy).

Ported from a-share-investment-system/services/quant_analyzers.py.

Porting notes:
  - 去除 BaseService/emit_log 依赖,改用 stdlib logging + dict 返回
  - 保留 6 位大师的评分算法: buffett / graham / lynch / taleb / munger / pabrai
  - 保留 DCF / 所有者收益估值算法

设计依据: ai-hedge-fund 的 17 位大师 + 本土化评分
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def buffett_analyze(stock_code: str, f: dict[str, Any]) -> dict[str, Any]:
    """巴菲特框架:ROE + 安全边际 + 护城河评分。

    评分维度:
      - ROE 偏离度 (max 40): (ROE - 10) * 4
      - 安全边际 (max 30): graham_number > price 时加分
      - 护城河 (max 30): 毛利率 + 负债 + ROE
    """
    roe = float(f.get("roe", 0) or 0)
    debt_equity = float(f.get("debt_to_equity", 100) or 100)
    gross_margin = float(f.get("gross_margin", 0) or 0)
    eps = float(f.get("eps", 0) or 0)
    bvps = float(f.get("bvps", 0) or 0)
    price = float(f.get("price", 1) or 1)

    roe_score = min(40, max(0, (roe - 10) * 4))
    gn_raw = 22.5 * max(eps, 0.01) * max(bvps, 0.01)
    graham_number = math.sqrt(gn_raw) if eps > 0 and bvps > 0 else 0
    safety_margin = (graham_number - price) / graham_number * 100 if graham_number > 0 else 0
    margin_score = min(30, max(0, safety_margin + 50))

    moat_score = 0
    if gross_margin > 40:
        moat_score += 10
    if debt_equity < 50:
        moat_score += 10
    if roe > 15:
        moat_score += 10

    total = roe_score + margin_score + moat_score
    return {
        "analyst": "buffett",
        "stock_code": stock_code,
        "score": min(100, total),
        "signal": "bullish" if total >= 60 else "bearish" if total < 30 else "neutral",
        "details": {
            "roe": roe,
            "roe_score": roe_score,
            "graham_number": round(graham_number, 2),
            "safety_margin_pct": round(safety_margin, 1),
            "margin_score": margin_score,
            "moat_score": moat_score,
        },
    }


def graham_analyze(stock_code: str, f: dict[str, Any]) -> dict[str, Any]:
    """格雷厄姆框架:净流动资产 + PE + PB 防御标准。

    当 NCAV 数据缺失时降级为 PE/PB 评分, 最低保底 40 分 (避免因数据缺而极端看空)。
    """
    current_assets = float(f.get("current_assets", 0) or 0)
    total_liabilities = float(f.get("total_liabilities", 0) or 0)
    shares = float(f.get("shares_outstanding", 0) or 0)
    price = float(f.get("price", 1) or 1)
    pe = float(f.get("pe_ratio", 0) or 0)

    has_ncav = current_assets > 0 and total_liabilities > 0 and shares > 0
    score = 0

    if has_ncav:
        ncav = (current_assets - total_liabilities) / shares
        ncav_discount = (ncav - price) / price * 100 if price > 0 else 0
        if ncav > price * 0.67:
            score += 50
        elif ncav > 0:
            score += 20
    else:
        ncav = 0
        ncav_discount = 0

    pe_ok = 0 < pe < 15
    if pe_ok:
        score += 30
    elif 0 < pe < 25:
        score += 15

    pb = float(f.get("pb_ratio", 0) or 0)
    if not has_ncav and 0 < pb < 1.5:
        score += 20
    elif not has_ncav and 0 < pb < 3:
        score += 10

    if not has_ncav and score < 30:
        score = max(score, 40)

    return {
        "analyst": "graham",
        "stock_code": stock_code,
        "score": min(100, score),
        "signal": "bullish" if score >= 60 else "bearish" if score < 30 else "neutral",
        "details": {
            "ncav_per_share": round(ncav, 2),
            "ncav_discount_pct": round(ncav_discount, 1),
            "pe_ok": pe_ok,
            "has_ncav_data": has_ncav,
        },
    }


def lynch_analyze(stock_code: str, f: dict[str, Any]) -> dict[str, Any]:
    """彼得·林奇框架:PEG + 业务简单性。"""
    pe = float(f.get("pe_ratio", 100) or 100)
    earnings_growth = float(f.get("earnings_growth_3y", 5) or 5)
    peg = pe / max(earnings_growth, 0.1)

    score = 0
    if peg < 0.5:
        score += 50
    elif peg < 1.0:
        score += 35
    elif peg < 1.5:
        score += 20

    if earnings_growth > 15:
        score += 25
    elif earnings_growth > 10:
        score += 15
    elif earnings_growth > 0:
        score += 8

    if score < 20 and 0 < pe < 30:
        score = max(score, 30)
    if score < 20 and 0 < pe < 50:
        score = max(score, 20)

    return {
        "analyst": "lynch",
        "stock_code": stock_code,
        "score": min(100, score),
        "signal": "bullish" if score >= 50 else "neutral",
        "details": {"peg": round(peg, 2), "earnings_growth_3y": earnings_growth, "pe": pe},
    }


def taleb_analyze(stock_code: str, f: dict[str, Any]) -> dict[str, Any]:
    """塔勒布框架:反脆弱性 + 尾部风险。"""
    debt_equity = float(f.get("debt_to_equity", 0) or 0)
    cash_ratio = float(f.get("cash_ratio", f.get("cash_to_assets", 0)) or 0)
    if cash_ratio == 0:
        current_ratio = float(f.get("current_ratio", 0) or 0)
        if current_ratio > 0:
            cash_ratio = min(current_ratio * 10, 50)

    anti_fragile = 0
    if debt_equity < 30:
        anti_fragile += 35
    elif debt_equity < 60:
        anti_fragile += 20
    if cash_ratio > 20:
        anti_fragile += 35
    elif cash_ratio > 10:
        anti_fragile += 20
    if float(f.get("gross_margin", 0) or 0) > 40:
        anti_fragile += 30

    return {
        "analyst": "taleb",
        "stock_code": stock_code,
        "score": min(100, anti_fragile),
        "signal": "bullish"
        if anti_fragile >= 60
        else "bearish"
        if anti_fragile < 30
        else "neutral",
        "details": {
            "debt_equity": debt_equity,
            "cash_to_assets": cash_ratio,
            "anti_fragile_score": anti_fragile,
        },
    }


def munger_analyze(stock_code: str, f: dict[str, Any]) -> dict[str, Any]:
    """芒格框架:ROIC 稳定性 + 管理层质量代理。"""
    roe = float(f.get("roe", 0) or 0)
    roe_stability = float(f.get("roe_stability_5y", 5) or 5)
    insider_holding = float(f.get("insider_holding_pct", 0) or 0)

    score = 0
    if roe > 15:
        score += 35
    elif roe > 10:
        score += 20
    if roe_stability < 3:
        score += 30
    if insider_holding > 5:
        score += 20
    elif insider_holding > 1:
        score += 10

    return {
        "analyst": "munger",
        "stock_code": stock_code,
        "score": min(100, score),
        "signal": "bullish" if score >= 55 else "neutral",
        "details": {
            "roe": roe,
            "roe_stability_5y": roe_stability,
            "insider_holding_pct": insider_holding,
        },
    }


def pabrai_analyze(stock_code: str, f: dict[str, Any]) -> dict[str, Any]:
    """帕布莱框架:低风险高回报不对称机会 (低 PB + 高 ROE)。"""
    price = float(f.get("price", 1) or 1)
    book_value = float(f.get("bvps", 1) or 1)
    roe = float(f.get("roe", 0) or 0)

    pb = price / max(book_value, 0.01)
    score = 0
    if pb < 1.0:
        score += 40
    elif pb < 1.5:
        score += 25
    if roe > 15:
        score += 35
    elif roe > 10:
        score += 20

    return {
        "analyst": "pabrai",
        "stock_code": stock_code,
        "score": min(100, score),
        "signal": "bullish" if score >= 55 else "neutral",
        "details": {"pb": round(pb, 2), "roe": roe},
    }


# ═══════════════════════════════════════════════════════════
#  DCF / 所有者收益估值引擎
# ═══════════════════════════════════════════════════════════


def calculate_dcf_intrinsic_value(
    free_cash_flow: float,
    growth_rate: float = 0.05,
    discount_rate: float = 0.10,
    terminal_growth_rate: float = 0.02,
    num_years: int = 5,
) -> float:
    """经典 DCF 估值: 5 年显性增长 + Gordon 永续增长。"""
    if free_cash_flow is None or free_cash_flow <= 0:
        return 0
    pv = sum(
        free_cash_flow * (1 + growth_rate) ** yr / (1 + discount_rate) ** yr
        for yr in range(1, num_years + 1)
    )
    final_fcf = free_cash_flow * (1 + growth_rate) ** num_years
    term_val = final_fcf * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
    pv_term = term_val / (1 + discount_rate) ** num_years
    return pv + pv_term


def calculate_owner_earnings(
    net_income: float,
    depreciation: float,
    capex: float,
    working_capital_change: float = 0,
) -> float:
    """巴菲特所有者收益 = 净利润 + 折旧 - 维护性 CAPEX - 营运资本变动。

    假设: 维护性 CAPEX 取 max(85% of CAPEX, 折旧), 反映"为维持业务不得不花的资本支出"。
    """
    maintenance_capex = abs(capex) * 0.85
    if depreciation > 0:
        maintenance_capex = max(maintenance_capex, depreciation)
    return net_income + depreciation - maintenance_capex - working_capital_change


def calculate_three_stage_dcf(
    net_income: float,
    depreciation: float,
    capex: float,
    working_capital_change: float,
    shares_outstanding: float,
    earnings_growth_3y: float = 0.05,
    stage1_growth_cap: float = 0.08,
    stage1_floor: float = 0.02,
    stage1_years: int = 5,
    terminal_growth: float = 0.025,
    discount_rate: float = 0.10,
    safety_margin: float = 0.15,
) -> dict[str, Any]:
    """三阶段 DCF (Buffett deep intrinsic value)。

    Stage 1 (5年): earnings_growth_3y * 0.7 (cap 8%, floor 2%)
    Stage 2 (5年): Stage1 增长率 * 0.5
    Terminal: 2.5% 永续增长
    折现率: 10%
    安全边际: 15% 折价
    """
    if shares_outstanding <= 0:
        return {"intrinsic_value": None, "details": "shares_outstanding missing"}
    owner_earnings = calculate_owner_earnings(
        net_income, depreciation, capex, working_capital_change
    )
    if owner_earnings <= 0:
        return {"intrinsic_value": None, "details": "owner_earnings <= 0"}

    stage1_growth = min(stage1_growth_cap, max(stage1_floor, earnings_growth_3y * 0.7))
    stage2_growth = stage1_growth * 0.5

    stage1_pv = sum(
        owner_earnings * (1 + stage1_growth) ** y / (1 + discount_rate) ** y
        for y in range(1, stage1_years + 1)
    )
    final_oe = owner_earnings * (1 + stage1_growth) ** stage1_years
    terminal_value = final_oe * (1 + terminal_growth) / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / (1 + discount_rate) ** stage1_years

    total_iv = (stage1_pv + terminal_pv) * (1 - safety_margin)
    iv_per_share = total_iv / shares_outstanding

    return {
        "intrinsic_value": round(iv_per_share, 2),
        "raw_iv": round((stage1_pv + terminal_pv) / shares_outstanding, 2),
        "owner_earnings": round(owner_earnings, 0),
        "assumptions": {
            "stage1_growth": round(stage1_growth, 3),
            "stage2_growth": round(stage2_growth, 3),
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
        },
        "details": (
            f"3-stage DCF: growth {stage1_growth:.1%}->{stage2_growth:.1%}->"
            f"{terminal_growth:.1%}, discount {discount_rate:.0%}"
        ),
    }


# ═══════════════════════════════════════════════════════════
#  一站式分析入口
# ═══════════════════════════════════════════════════════════


def analyze_all(stock_code: str, financials: dict[str, Any]) -> list[dict[str, Any]]:
    """对单只股票运行全部 6 位大师分析。

    Args:
        stock_code: 股票代码
        financials: 基本面 dict (roe, pe, pb, eps, bvps, debt_to_equity, gross_margin, etc.)

    Returns:
        6 个分析结果列表, 每个含 analyst/score/signal/details
    """
    results: list[dict[str, Any]] = []
    analyzers = [
        ("buffett", buffett_analyze),
        ("graham", graham_analyze),
        ("lynch", lynch_analyze),
        ("taleb", taleb_analyze),
        ("munger", munger_analyze),
        ("pabrai", pabrai_analyze),
    ]
    for name, fn in analyzers:
        try:
            results.append(fn(stock_code, financials))
        except Exception as e:
            logger.warning("%s_analyze(%s) failed: %s", name, stock_code, e)
            results.append({
                "analyst": name,
                "stock_code": stock_code,
                "score": 50,
                "signal": "neutral",
                "details": {"error": str(e)[:200]},
            })
    return results


def aggregate_consensus(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """对多大师结果加权汇总为综合意见。"""
    if not analyses:
        return {"consensus": "neutral", "average_score": 50, "signals": {}}
    total = 0
    weight = 0
    signals: dict[str, int] = {"bullish": 0, "neutral": 0, "bearish": 0}
    for a in analyses:
        score = a.get("score", 50)
        if score >= 60:
            signals["bullish"] += 1
        elif score < 30:
            signals["bearish"] += 1
        else:
            signals["neutral"] += 1
        total += score
        weight += 1
    avg = total / weight if weight else 50
    consensus = "bullish" if avg >= 60 else "bearish" if avg < 30 else "neutral"
    return {
        "consensus": consensus,
        "average_score": round(avg, 1),
        "signals": signals,
        "num_analysts": len(analyses),
    }
