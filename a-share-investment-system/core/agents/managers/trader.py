"""交易员Agent — 预留"""

from typing import Any


def plan_trade(code: str, date: str, analysis: dict | None = None) -> dict[str, Any]:
    return {"analyst": "trader", "confidence": 0, "summary": "交易员暂未接入"}
