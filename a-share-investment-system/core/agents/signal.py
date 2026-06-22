"""结构化信号提取"""

from typing import Any


def process_signal(decision: dict) -> dict[str, Any]:
    if not decision:
        return {"action": "hold", "confidence": 0, "reason": "无决策"}
    return {
        "action": decision.get("action", "hold"),
        "confidence": decision.get("confidence", 0.5),
        "reason": decision.get("reason", ""),
        "position_size": decision.get("position_size", "观望"),
    }
