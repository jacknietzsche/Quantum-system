"""反思引擎。

设计依据: S09 §9.2。
当交易结果已知时，自动反思。
"""

from __future__ import annotations

import logging

from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


def reflect(llm_client: LLMClient, decision: dict, outcome: dict) -> str:
    """
    自动反思决策。

    Args:
        decision: {action, ticker, entry_price, thesis}
        outcome: {profit, return_pct}

    Returns:
        反思文本（100字以内）
    """
    profit = outcome.get("profit", 0)
    return_pct = outcome.get("return_pct", 0)

    prompt = f"""
    决策: {decision.get("action")} {decision.get("ticker")} @ {decision.get("entry_price")}
    论据: {decision.get("thesis")}
    结果: {"盈利" if profit > 0 else "亏损"} {abs(profit):.2f}元 ({return_pct:.1f}%)
    请分析这个决策，给出100字以内的反思。
    """

    try:
        response = llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            agent_name="reflection",
            ticker=decision.get("ticker", ""),
        )
        return response.content
    except Exception as e:
        logger.warning("反思生成失败: %s", e)
        return f"反思生成失败: {e}"
