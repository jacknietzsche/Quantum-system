"""Agent权重自适应

根据 Agent 历史表现和市场状态动态调整各 Agent 的权重。
"""

from __future__ import annotations

import logging

from services.screening.daily_memory import DailyMemory

logger = logging.getLogger(__name__)

# Agent 风格分类
_AGGRESSIVE_AGENTS = {"cathie_wood", "limit_up_master", "momentum_master"}
_DEFENSIVE_AGENTS = {"michael_burry", "howard_marks", "risk_sentinel", "bill_ackman"}
_MOMENTUM_AGENTS = {"momentum_master", "stanley_druckenmiller", "peter_lynch_growth"}


class WeightAdapter:
    """根据Agent历史表现动态调整权重"""

    def __init__(self, memory: DailyMemory | None = None):
        self._memory = memory or DailyMemory()

    def adapt_weights(
        self,
        base_weights: dict[str, float],
        market_regime: str = "NEUTRAL",
    ) -> dict[str, float]:
        """读取 agent_stats -> 计算近期准确率 -> 调整权重

        逻辑:
        - 准确率 > 60%: 权重 x 1.2
        - 准确率 < 40%: 权重 x 0.7
        - 数据不足(新Agent): 保持默认
        - 熊市时避险Agent权重 x 1.3, 激进Agent x 0.7
        - 牛市时动量Agent权重 x 1.3
        - 归一化: 所有权重之和保持 1.0

        Args:
            base_weights: 基础权重字典 {agent_name: weight}
            market_regime: 市场状态 (BULL/BEAR/NEUTRAL/PANIC/EUPHORIA)

        Returns:
            dict: 调整后的权重 {agent_name: weight}
        """
        if not base_weights:
            return {}

        try:
            accuracy = self._get_accuracy()
            adjusted = self._apply_accuracy_adjustment(base_weights, accuracy)
            self._apply_regime_adjustment(adjusted, market_regime.upper())
            self._normalize(adjusted)
            return adjusted
        except Exception as e:
            logger.warning("WeightAdapter.adapt_weights failed: %s", e)
            return dict(base_weights)

    def _apply_accuracy_adjustment(
        self,
        base_weights: dict[str, float],
        accuracy: dict[str, dict],
    ) -> dict[str, float]:
        """根据历史准确率调整权重"""
        adjusted = dict(base_weights)
        for agent_name, weight in adjusted.items():
            acc = accuracy.get(agent_name, {})
            hit_rate = acc.get("accuracy", 0)
            total = acc.get("total_picks", 0)

            if total < 3:
                continue

            if hit_rate > 0.6:
                adjusted[agent_name] = weight * 1.2
            elif hit_rate < 0.4:
                adjusted[agent_name] = weight * 0.7
        return adjusted

    def _apply_regime_adjustment(
        self,
        adjusted: dict[str, float],
        regime: str,
    ) -> None:
        """根据市场状态调整权重 (in-place)"""
        if regime in ("BEAR", "PANIC"):
            agents = _DEFENSIVE_AGENTS
            factor = 1.3
            anti_factor = 0.7
            anti_agents = _AGGRESSIVE_AGENTS
        elif regime in ("BULL", "EUPHORIA"):
            agents = _MOMENTUM_AGENTS
            factor = 1.3
            anti_factor = None
            anti_agents = set()
        else:
            return

        for agent_name in adjusted:
            if agent_name in agents:
                adjusted[agent_name] *= factor
            elif anti_factor is not None and agent_name in anti_agents:
                adjusted[agent_name] *= anti_factor

    def _normalize(self, adjusted: dict[str, float]) -> None:
        """归一化权重 (in-place)"""
        total = sum(adjusted.values())
        if total > 0:
            for agent_name in list(adjusted):
                adjusted[agent_name] = round(adjusted[agent_name] / total, 4)

    def _get_accuracy(self) -> dict[str, dict]:
        """从 agent_stats 获取准确率数据"""
        try:
            stats = self._memory.get_agent_stats()
            result: dict[str, dict] = {}
            for s in stats:
                name = s.get("agent_name", "")
                total = int(s.get("total_picks", 0))
                correct = int(s.get("correct", 0))
                result[name] = {
                    "accuracy": correct / max(total, 1),
                    "total_picks": total,
                    "correct": correct,
                }
            return result
        except Exception as e:
            logger.warning("get_accuracy failed: %s", e)
            return {}
