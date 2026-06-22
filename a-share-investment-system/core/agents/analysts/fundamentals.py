"""基本面分析Agent"""

from ..toolkit import get_fundamentals


def analyze_fundamentals(code: str, date: str) -> dict:
    f = get_fundamentals(code)
    if not f or not f.get("roe"):
        return {"analyst": "fundamentals", "confidence": 0, "summary": "基本面数据不足"}
    score = 50
    if f["roe"] > 15:
        score += 15
    if f.get("pe_ratio") and 5 < f["pe_ratio"] < 20:
        score += 10
    if f.get("gross_margin", 0) > 40:
        score += 8
    if f.get("debt_to_equity", 100) < 50:
        score += 7
    return {
        "analyst": "fundamentals",
        "confidence": 0.6,
        "summary": f"ROE={f['roe']:.1f}%, PE={f.get('pe_ratio', 0):.1f}",
        "score": score,
        "data": f,
    }
