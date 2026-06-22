"""记忆注入。

设计依据: S09 §9.3。
每次新分析前，注入历史记忆。
"""

from __future__ import annotations

from memory.decision_log import DecisionLog


def inject_memory(decision_log: DecisionLog, ticker: str, limit: int = 5) -> str:
    """
    注入历史记忆到Agent prompt。

    Args:
        ticker: 股票代码
        limit: 最多返回的历史条数

    Returns:
        记忆文本（Markdown格式）
    """
    history = decision_log.get_history(ticker, limit=limit)
    if not history:
        return ""

    memory = "## 历史决策记忆\n\n"
    for h in history:
        memory += f"- {h.get('date', 'N/A')}: {h.get('action', 'N/A')} @ {h.get('entry_price', 0)}"
        if h.get("reflection"):
            memory += f" — 反思: {h['reflection']}"
        memory += "\n"

    return memory
