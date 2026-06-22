"""Stage2: 四维评分 — 趋势质量 / 资金行为 / AI基本面 / 防御性

废弃旧版对 ROE/PE/毛利率/营收增长的硬依赖。
新评分体系在财务数据缺失时仍能给出有效分数。
"""

from __future__ import annotations

from typing import Any

from shared.logging import emit_log


def stage2_fundamental_filter(
    candidates: list[dict],
    config: Any,
    style: str = "hybrid",
    weights: dict[str, float] | None = None,
) -> list[dict]:
    """第二级: 四维综合评分

    Args:
        candidates: Stage1 输出的候选股
        config: Stage2Config
        style: 选股风格
        weights: 动态权重 (来自市场感知), 如 {"trend":0.35, "capital":0.25, ...}
                 为None时使用默认权重。
    """
    passed = []
    for stock in candidates:
        dims = _score_all_dimensions(stock, config, style, weights)
        total = dims["total"]
        if total >= config.score_min:
            stock["_stage2_score"] = total
            stock["_stage2_dims"] = dims
            passed.append(stock)

    passed.sort(key=lambda x: x.get("_stage2_score", 0), reverse=True)
    result = passed[: config.top_n]
    emit_log(
        "INFO",
        "screening",
        f"[{style}] Stage2: {len(candidates)}->{len(result)} "
        f"(top_score={result[0].get('_stage2_score', 0) if result else 'N/A'})",
    )
    return result


def _score_all_dimensions(
    stock: dict,
    config: Any,
    style: str,
    weights: dict[str, float] | None = None,
) -> dict:
    """四维评分, 每维 0-10, 加权总分

    Args:
        weights: 来自市场感知的动态权重, 如 {"trend":0.35, "capital":0.25, ...}
    """
    w = weights or {"trend": 0.35, "capital": 0.25, "fundamental": 0.25, "defensive": 0.15}

    trend = _trend_quality(stock, style)
    capital = _capital_behavior(stock, style)
    fundamental = _ai_fundamental(stock, style)
    defensive = _defensive_quality(stock, style)

    total = (
        trend["score"] * w.get("trend", 0.25)
        + capital["score"] * w.get("capital", 0.25)
        + fundamental["score"] * w.get("fundamental", 0.25)
        + defensive["score"] * w.get("defensive", 0.25)
    )

    return {
        "trend": round(trend["score"], 1),
        "capital": round(capital["score"], 1),
        "fundamental": round(fundamental["score"], 1),
        "defensive": round(defensive["score"], 1),
        "total": round(total, 1),
        "signals": trend.get("signals", []) + capital.get("signals", []),
    }


def _trend_quality(stock: dict, style: str) -> dict:
    """趋势质量 (0-10): 均线排列 + RSI + MACD + 波动率压缩

    完全不依赖基本面数据, 仅用量价。
    """
    score = 5.0
    signals = []

    ma5 = stock.get("ma5", 0)
    ma10 = stock.get("ma10", 0)
    ma20 = stock.get("ma20", 0)
    ma60 = stock.get("ma60", 0)
    price = stock.get("latest_price", 0)

    if ma5 > 0 and ma10 > 0 and ma20 > 0 and ma60 > 0:
        if ma5 > ma10 > ma20 > ma60:
            score += 2.5
            signals.append("均线多头排列")
        elif ma5 > ma10 > ma20:
            score += 1.0
            signals.append("短中期均线上行")
        elif ma5 < ma10 < ma20 < ma60:
            score -= 1.5
            signals.append("均线空头排列")
        elif price < ma20:
            score -= 0.5
            signals.append("跌破20日均线")

    # RSI
    rsi = stock.get("rsi_14", 50)
    if rsi > 0:
        if 40 < rsi < 60:
            score += 1.0
            signals.append("RSI中性偏强")
        elif 60 <= rsi < 80:
            score += 2.0
            signals.append("RSI强势区")
        elif rsi >= 80:
            score -= 1.0
            signals.append("RSI超买(警惕)")
        elif rsi <= 30:
            score += 1.0
            signals.append("RSI超卖(反弹机会)")

    # MACD
    macd = stock.get("macd", 0)
    if macd != 0:
        if macd > 0:
            score += 0.5
            signals.append("MACD正值")
        else:
            score -= 0.5
            signals.append("MACD负值")

    vol = stock.get("volatility_20d", 0)
    if vol > 0:
        if vol < 0.15:
            score -= 1.0
            signals.append("波动率过低(织布机)")
        elif vol > 0.6:
            score -= 0.5
            signals.append("波动率过高")

    # 近期涨跌幅
    chg = stock.get("change_pct", 0)
    if chg > 5:
        score += 1.0
        signals.append("近期强势上涨")
    elif chg < -8:
        score -= 1.0
        signals.append("近期大跌")

    return {"score": max(0, min(10, score)), "signals": signals}


def _capital_behavior(stock: dict, style: str) -> dict:
    """资金行为 (0-10): 量比 + 换手率 + 成交额

    衡量市场对该股票的资金关注度。
    """
    score = 5.0
    signals = []

    amt = stock.get("amount", 0)
    tr = stock.get("turnover_rate", 0)

    # 成交额活性
    if amt > 0:
        if amt >= 1e9:  # 10亿+
            score += 2.0
            signals.append("巨量成交(主力关注)")
        elif amt >= 3e8:  # 3亿+
            score += 1.0
            signals.append("量能充足")
        elif amt < 2e7:  # 2000万以下
            score -= 1.5
            signals.append("成交低迷(僵尸)")

    # 换手率
    if tr > 0:
        if 1 <= tr <= 10:
            score += 1.0
            signals.append("换手率适中活跃")
        elif tr > 15:
            score -= 0.5
            signals.append("换手率过高(换庄/出货)")
        elif tr < 0.3:
            score -= 1.0
            signals.append("换手率过低(冷门)")

    chg = stock.get("change_pct", 0)
    if chg > 0 and amt > 3e8:
        score += 1.0
        signals.append("价涨量增(健康)")
    elif chg < -3 and tr > 10:
        score -= 0.5
        signals.append("价跌量增(出货嫌疑)")

    # zzshare 热度因子
    code = stock.get("stock_code", "")
    if code:
        _hot_bonus = stock.get("_zzshare_bonus", 0)
        if _hot_bonus:
            score += _hot_bonus * 0.5

    return {"score": max(0, min(10, score)), "signals": signals}


def _ai_fundamental(stock: dict, style: str) -> dict:
    """AI/规则基本面 (0-10): 不依赖精确财务数据

    使用 ai_analyst 模块进行规则推理, 可选LLM增强。
    """
    try:
        from services.screening.ai_analyst import score_from_available_data

        result = score_from_available_data(stock)
        return {"score": result["score"], "signals": result.get("signals", [])}
    except Exception:
        score = 5.0
        if stock.get("market_cap", 0) >= 200:
            score += 1
        if 0 < stock.get("pe", 0) < 30:
            score += 1
        if stock.get("amount", 0) >= 3e8:
            score += 1
        return {"score": max(0, min(10, score)), "signals": []}


def _defensive_quality(stock: dict, style: str) -> dict:
    """防御性/质量 (0-10): 回撤 + 波动 + 稳定性

    衡量下行风险, 对短线风格尤为重要。
    """
    score = 6.0  # 默认较高, 因为能进入候选池的已经是活跃标的
    signals = []

    mdd = stock.get("max_drawdown_60d", 0)
    vol = stock.get("volatility_20d", 0)
    mc = stock.get("market_cap", 0)

    # 最大回撤
    if mdd > 0:
        if mdd < 15:
            score += 1.5
            signals.append("回撤控制好")
        elif mdd > 35:
            score -= 1.5
            signals.append("近期回撤大")

    # 波动率稳定性
    if vol > 0:
        if vol < 0.2:
            score += 1.0
            signals.append("波动率低(稳健)")
        elif vol > 0.5:
            score -= 0.5
            signals.append("高波动(风险)")

    # 市值安全垫
    if mc >= 500:
        score += 1.0
        signals.append("大盘抗跌")
    elif mc > 0 and mc < 30:
        score -= 1.0
        signals.append("小盘脆弱")

    return {"score": max(0, min(10, score)), "signals": signals}
