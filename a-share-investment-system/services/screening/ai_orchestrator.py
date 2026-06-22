"""AI Orchestrator — Stage 3 与 Stage 4 之间的认知引擎

功能:
  1. 接收Stage3结果 + 市场状态
  2. 用AI动态调整候选股评分（非LLM路径用规则")
  3. 输出增强后的候选股列表 + AI解读
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _rule_adjust(candidates: list[dict], market_state: dict) -> list[dict]:
    """规则驱动的评分调整（无LLM时的降级路径）"""
    regime = market_state.get("regime", "NEUTRAL")

    for stock in candidates:
        score = stock.get("score", 50)

        # 市场状态调整
        if regime in ("BEAR", "PANIC"):
            # 熊市/恐慌: 偏好低PE+高ROE防御股
            pe = stock.get("pe_ratio", 0) or 0
            roe = stock.get("roe", 0) or 0
            if 0 < pe < 15 and roe > 10:
                score = min(100, score * 1.15)
            elif pe > 40 or roe <= 0:
                score *= 0.85
        elif regime == "BULL":
            chg = stock.get("change_pct_20d", 0) or 0
            if chg > 10:
                score = min(100, score * 1.1)
        # 震荡/分化: 偏好价值+质量
        elif (stock.get("pe_ratio", 0) or 0) > 0 and (stock.get("pb_ratio", 0) or 0) > 0:
            pe_pb = abs(stock.get("pe_ratio", 20)) * abs(stock.get("pb_ratio", 2))
            if 10 < pe_pb < 200:
                score = min(100, score * 1.05)

        stock["score"] = round(score, 1)
        stock["orchestrator_note"] = f"market={regime}"

    # 按新评分排序
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    return candidates


class AIOrchestrator:
    """AI Orchestrator — 认知推理引擎

    在Stage3和Stage4之间运行:
    - 输入: Stage3候选股 + 市场状态
    - 处理: AI评分调整 / 规则评分调整
    - 输出: 增强候选股 + AI解读
    """

    def __init__(self, llm_client: Any | None = None):
        self._llm = llm_client

    def process(self, candidates: list[dict], market_state: dict) -> dict:
        """处理候选股"""
        if not candidates:
            return {"candidates": [], "insight": ""}

        # 规则调整（始终运行）
        adjusted = _rule_adjust(candidates, market_state)

        # AI深度解读（有LLM时启用）
        insight = ""
        if self._llm:
            insight = self._ai_insight(adjusted, market_state)

        return {"candidates": adjusted, "insight": insight}

    def _ai_insight(self, candidates: list[dict], market_state: dict) -> str:
        """AI对候选股的整体解读"""
        try:
            top5 = candidates[:5]
            lines = [
                f"{s.get('stock_code', '')} {s.get('stock_name', '')} score={s.get('score', 0)}"
                for s in top5
            ]
            prompt = f"""市场状态: {market_state.get("regime")}
今日选股前5名:
{chr(10).join(lines)}

请用1-2句话评估这个组合的风险和机会。"""
            return str(self._llm.chat(prompt))[:500]
        except Exception as e:
            logger.debug("AI insight failed: %s", e)
            return ""
