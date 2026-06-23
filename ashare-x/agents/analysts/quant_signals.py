"""分析师量化预信号。

在调用 LLM 之前，对原始数据做一层定量计算，
生成一个简短、可解释的预信号（pre-signal）注入 prompt。
这既加深了分析逻辑，又为 LLM 提供了先验约束。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _safe(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def compute_technical_signal(indicators: dict[str, Any] | None) -> dict[str, Any]:
    """基于技术指标计算预信号。"""
    if not indicators:
        return {"signal": "neutral", "confidence": 50, "reason": "无指标数据"}

    ma5 = _safe(indicators.get("ma5"))
    ma20 = _safe(indicators.get("ma20"))
    ma60 = _safe(indicators.get("ma60"))
    macd = _safe(indicators.get("macd"))
    rsi = _safe(indicators.get("rsi_14"))
    close = _safe(indicators.get("close"))
    upper = _safe(indicators.get("boll_upper"))
    lower = _safe(indicators.get("boll_lower"))

    score = 50
    reasons: list[str] = []

    if ma5 and ma20 and ma5 > ma20:
        score += 10
        reasons.append("MA5>MA20（短期多头排列）")
    elif ma5 and ma20 and ma5 < ma20:
        score -= 10
        reasons.append("MA5<MA20（短期空头排列）")

    if ma20 and ma60 and ma20 > ma60:
        score += 10
        reasons.append("MA20>MA60（中期多头）")
    elif ma20 and ma60 and ma20 < ma60:
        score -= 10
        reasons.append("MA20<MA60（中期空头）")

    if macd > 0:
        score += 8
        reasons.append("MACD>0")
    elif macd < 0:
        score -= 8
        reasons.append("MACD<0")

    if rsi > 70:
        score -= 12
        reasons.append("RSI超买")
    elif rsi < 30:
        score += 12
        reasons.append("RSI超卖")

    if close and upper and lower and upper > lower:
        if close > upper:
            score -= 8
            reasons.append("价格突破布林上轨")
        elif close < lower:
            score += 8
            reasons.append("价格触及布林下轨")

    score = max(0, min(100, score))
    if score >= 60:
        signal = "bullish"
    elif score <= 40:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "signal": signal,
        "confidence": score,
        "reason": "；".join(reasons) if reasons else "指标中性",
    }


def compute_fundamental_signal(fund: dict[str, Any] | None) -> dict[str, Any]:
    """基于基本面计算预信号。"""
    if not fund:
        return {"signal": "neutral", "confidence": 50, "reason": "无基本面数据"}

    pe = _safe(fund.get("pe_ratio"))
    pb = _safe(fund.get("pb_ratio"))
    roe = _safe(fund.get("roe"))
    gross = _safe(fund.get("gross_margin"))
    rev_yoy = _safe(fund.get("revenue_yoy"))
    profit_yoy = _safe(fund.get("net_income_yoy"))
    debt = _safe(fund.get("debt_to_equity"))

    score = 50
    reasons: list[str] = []

    # 估值：PE/PB 越低越利好（仅当为正）
    if 0 < pe < 20:
        score += 12
        reasons.append("PE<20，估值偏低")
    elif pe > 60:
        score -= 10
        reasons.append("PE>60，估值偏高")

    if 0 < pb < 2:
        score += 8
        reasons.append("PB<2")
    elif pb > 6:
        score -= 8
        reasons.append("PB>6")

    # 盈利能力
    if roe > 15:
        score += 10
        reasons.append("ROE>15%，盈利能力强")
    elif 0 < roe < 8:
        score -= 8
        reasons.append("ROE<8%")

    if gross > 30:
        score += 6
        reasons.append("毛利率>30%")

    # 成长性
    if rev_yoy > 20:
        score += 8
        reasons.append("营收高增长")
    elif rev_yoy < -10:
        score -= 8
        reasons.append("营收下滑")

    if profit_yoy > 20:
        score += 8
        reasons.append("利润高增长")
    elif profit_yoy < -10:
        score -= 8
        reasons.append("利润下滑")

    # 财务健康
    if 0 < debt < 50:
        score += 5
        reasons.append("资产负债率适中")
    elif debt > 80:
        score -= 8
        reasons.append("资产负债率过高")

    score = max(0, min(100, score))
    signal = "bullish" if score >= 60 else "bearish" if score <= 40 else "neutral"
    return {
        "signal": signal,
        "confidence": score,
        "reason": "；".join(reasons) if reasons else "基本面中性",
    }


def compute_news_signal(news: list[dict[str, Any]] | None) -> dict[str, Any]:
    """基于新闻标题做简单情感预打分。"""
    if not news:
        return {"signal": "neutral", "confidence": 50, "reason": "无新闻数据"}

    pos_words = [
        "利好", "增长", "盈利", "超预期", "签约", "中标", "回购", "增持",
        "改革", "突破", "创新", "扩产", "涨价", "景气",
    ]
    neg_words = [
        "利空", "下滑", "亏损", "暴雷", "减持", "监管", "处罚", "立案",
        "退市", "风险", "警示", "债务", "违约", "裁员",
    ]

    pos = neg = 0
    for n in news:
        title = str(n.get("title", ""))
        for w in pos_words:
            pos += len(re.findall(w, title))
        for w in neg_words:
            neg += len(re.findall(w, title))

    total = pos + neg
    if total == 0:
        return {"signal": "neutral", "confidence": 50, "reason": f"{len(news)}条新闻，情感中性"}

    score = 50 + int((pos - neg) / total * 30)
    score = max(0, min(100, score))
    signal = "bullish" if score >= 60 else "bearish" if score <= 40 else "neutral"
    return {
        "signal": signal,
        "confidence": score,
        "reason": f"{len(news)}条新闻，正/负面词 {pos}/{neg}",
    }


def compute_sentiment_signal(sent: dict[str, Any] | None) -> dict[str, Any]:
    """基于情绪/资金流计算预信号。"""
    if not sent:
        return {"signal": "neutral", "confidence": 50, "reason": "无情绪数据"}

    score = 50
    reasons: list[str] = []

    ff = sent.get("fund_flow") or {}
    main_net = _safe(ff.get("main_net_inflow"))
    main_pct = _safe(ff.get("main_net_pct"))
    if main_net > 0:
        score += 10
        reasons.append(f"主力净流入 {main_net:.0f}")
    elif main_net < 0:
        score -= 10
        reasons.append(f"主力净流出 {main_net:.0f}")

    if main_pct > 5:
        score += 8
        reasons.append("主力净占比>5%")
    elif main_pct < -5:
        score -= 8
        reasons.append("主力净占比<-5%")

    north = sent.get("north_flow")
    if north is not None:
        north_f = _safe(north)
        if north_f > 0:
            score += 6
            reasons.append("北向增持")
        elif north_f < 0:
            score -= 6
            reasons.append("北向减持")

    change = _safe(sent.get("change_pct"))
    if change > 5:
        score -= 8
        reasons.append("单日涨幅>5%，注意追高风险")
    elif change < -5:
        score += 5
        reasons.append("单日跌幅>5%，或存在超跌")

    score = max(0, min(100, score))
    signal = "bullish" if score >= 60 else "bearish" if score <= 40 else "neutral"
    return {
        "signal": signal,
        "confidence": score,
        "reason": "；".join(reasons) if reasons else "情绪中性",
    }
