"""Stage 0: AI市场环境感知 — 动态策略决策

在Stage1运行前执行，取代固定参数配置。
AI读取今日市场数据后决定：
  1. 当前市场状态（牛/熊/震荡/分化/风格切换）
  2. 今日最优策略方向
  3. 各阶段过滤阈值的动态调整系数
"""

import logging
from datetime import datetime
from typing import Any

from services.base import ServiceResult

logger = logging.getLogger(__name__)

# 市场状态枚举
MARKET_STATES = ["BULL", "BEAR", "NEUTRAL", "PANIC", "EUPHORIA", "DIVERGENCE", "STYLE_ROTATION"]


def _calc_market_score(market_data: dict) -> dict:
    """基于数据的市场评分（纯计算，不依赖AI）"""
    breadth = market_data.get("breadth", {})

    total = breadth.get("total", 1) or 1
    up_ratio = (breadth.get("up", 0) or 0) / total
    down_ratio = (breadth.get("down", 0) or 0) / total
    limit_up = breadth.get("limit_up", 0) or 0
    limit_down = breadth.get("limit_down", 0) or 0

    # 涨跌比评分 (-2 ~ +2)
    breadth_score = (up_ratio - down_ratio) * 4
    breadth_score = max(-2, min(2, breadth_score))

    # 涨停/跌停比评分
    lb_ratio = limit_up / max(limit_down, 1) if limit_down > 0 else limit_up / max(total * 0.01, 1)
    lb_score = min(2, lb_ratio * 0.5) if lb_ratio > 1 else max(-2, -(1 / max(lb_ratio, 0.01)) * 0.5)

    # 综合得分
    composite = breadth_score * 0.6 + lb_score * 0.4

    # 市场状态判定
    if composite >= 1.2:
        regime = "BULL"
    elif composite >= 0.3:
        regime = "NEUTRAL"
    elif composite >= -0.3:
        regime = "DIVERGENCE"
    elif composite >= -1.0:
        regime = "BEAR"
    else:
        regime = "PANIC"

    # 策略倾向
    if regime in ("BULL", "EUPHORIA"):
        strategy_bias = "momentum"
    elif regime in ("BEAR", "PANIC"):
        strategy_bias = "defensive"
    else:
        strategy_bias = "value"

    return {
        "regime": regime,
        "composite_score": round(composite, 3),
        "breadth_score": round(breadth_score, 3),
        "up_ratio": round(up_ratio, 3),
        "limit_up": limit_up,
        "limit_down": limit_down,
        "strategy_bias": strategy_bias,
        "timestamp": datetime.now().isoformat(),
    }


class MarketStateAI:
    """AI增强的市场环境感知

    流程:
    1. 先用规则计算基础市场评分
    2. AI在此基础上做深度解读（可选，有LLM时启用）
    3. 输出：市场状态 + 策略建议 + 阈值调整系数
    """

    def __init__(self, llm_client: Any | None = None):
        self._llm = llm_client

    def analyze(self, market_data: dict) -> ServiceResult:
        """完整市场分析"""
        try:
            base = _calc_market_score(market_data)

            # 有LLM时做深度解读
            ai_insight = {}
            if self._llm:
                ai_insight = self._ai_interpret(market_data, base)

            # 阈值调整系数（基于市场状态）
            adjustment = self._calc_adjustment(base["regime"])

            return ServiceResult.ok(
                data={
                    "regime": base["regime"],
                    "composite_score": base["composite_score"],
                    "strategy_bias": base["strategy_bias"],
                    "breadth": {
                        "up_ratio": base["up_ratio"],
                        "limit_up": base["limit_up"],
                        "limit_down": base["limit_down"],
                    },
                    "adjustment": adjustment,
                    "ai_insight": ai_insight,
                }
            )
        except Exception as e:
            logger.warning("MarketStateAI failed: %s", e)
            return ServiceResult.ok(
                data={
                    "regime": "NEUTRAL",
                    "composite_score": 0,
                    "strategy_bias": "value",
                    "adjustment": {
                        "stage1_top": 1.0,
                        "stage2_top": 1.0,
                        "stage3_top": 1.0,
                        "turnover_min": 1.0,
                    },
                }
            )

    def _calc_adjustment(self, regime: str) -> dict:
        """根据市场状态计算阈值调整系数"""
        if regime == "BULL":
            return {"stage1_top": 1.5, "stage2_top": 1.3, "stage3_top": 1.2, "turnover_min": 0.8}
        if regime == "BEAR":
            return {"stage1_top": 0.7, "stage2_top": 0.8, "stage3_top": 0.9, "turnover_min": 1.5}
        if regime == "PANIC":
            return {"stage1_top": 0.5, "stage2_top": 0.6, "stage3_top": 0.7, "turnover_min": 2.0}
        return {"stage1_top": 1.0, "stage2_top": 1.0, "stage3_top": 1.0, "turnover_min": 1.0}

    def _ai_interpret(self, market_data: dict, base: dict) -> dict:
        """AI深度解读（有LLM时启用）"""
        try:
            prompt = f"""作为A股市场策略师，分析今日市场状态：

指数数据: {market_data.get("indices", {})}
涨跌比: {base.get("up_ratio", 0):.1%}
涨停/跌停: {base["limit_up"]}/{base["limit_down"]}
计算状态: {base["regime"]}

请输出简短判断（2-3句话）：
1. 当前市场核心矛盾是什么
2. 今日应该重点规避什么风险
3. 有什么值得关注的板块信号"""
            response = self._llm.chat(prompt)
            return {"interpretation": str(response)[:500]}
        except Exception as e:
            logger.debug("AI market interpret failed: %s", e)
            return {}
