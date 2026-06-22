"""风险裁判Agent — 预留"""

from typing import Any


def judge_risk(code: str, date: str, debate_results: dict | None = None) -> dict[str, Any]:
    return {"analyst": "risk_judge", "confidence": 0, "summary": "风险裁判暂未接入"}
