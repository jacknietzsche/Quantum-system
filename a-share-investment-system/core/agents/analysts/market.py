"""行情分析Agent — 分析价格趋势和技术指标"""

from ..toolkit import get_indicators, get_market_regime, get_stock_data


def analyze_market(code: str, date: str) -> dict:
    data = get_stock_data(code)
    indicators = get_indicators(code)
    regime = get_market_regime()
    if not data:
        return {"analyst": "market", "confidence": 0, "summary": "数据不足"}
    signal = (
        "bullish"
        if indicators.get("trend") in ("上升", "bullish")
        else ("bearish" if indicators.get("trend") in ("下降", "bearish") else "neutral")
    )
    return {
        "analyst": "market",
        "confidence": 0.7,
        "summary": f"趋势:{signal}, 大盘:{regime}",
        "signal": signal,
        "data": {**data, **indicators, "regime": regime},
    }
