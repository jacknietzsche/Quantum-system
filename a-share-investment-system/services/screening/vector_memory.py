"""基于标签的简单向量记忆检索 (无需外部向量数据库)

将每日市场状态编码为特征标签组合, 通过标签匹配来检索相似历史.
"""

from __future__ import annotations

import logging

from services.screening.daily_memory import DailyMemory

logger = logging.getLogger(__name__)


class VectorMemory:
    """基于标签的相似记忆检索

    将每日市场状态编码为"特征向量"(简单标签组合),
    通过标签匹配来检索相似历史, 无需外部向量数据库.

    标签维度:
    - regime: 市场状态 (BULL/BEAR/NEUTRAL/PANIC/EUPHORIA)
    - score_bucket: 评分区间 (strong/positive/neutral/negative/extreme)
    - bias: 策略倾向 (momentum/defensive/value)
    - breadth: 宽度强度 (strong/normal/weak)
    """

    def __init__(self, memory: DailyMemory | None = None):
        self._memory = memory or DailyMemory()

    def encode_market(self, market_state: dict) -> dict:
        """将市场状态编码为检索标签

        Args:
            market_state: 市场状态字典, 包含 regime/composite_score/strategy_bias/breadth

        Returns:
            dict: 编码后的特征标签 {regime, score_bucket, bias, breadth}
        """
        regime = market_state.get("regime", "NEUTRAL")
        composite_score = market_state.get("composite_score", 0)
        strategy_bias = market_state.get("strategy_bias", "value")
        breadth_raw = market_state.get("breadth", {})
        up_ratio = breadth_raw.get("up_ratio", 0.5) if isinstance(breadth_raw, dict) else 0.5

        # 评分区间编码
        if composite_score >= 1.0:
            score_bucket = "strong"
        elif composite_score >= 0.3:
            score_bucket = "positive"
        elif composite_score >= -0.3:
            score_bucket = "neutral"
        elif composite_score >= -1.0:
            score_bucket = "negative"
        else:
            score_bucket = "extreme"

        # 宽度强度编码
        if up_ratio >= 0.6:
            breadth_label = "strong"
        elif up_ratio >= 0.4:
            breadth_label = "normal"
        else:
            breadth_label = "weak"

        return {
            "regime": regime,
            "score_bucket": score_bucket,
            "bias": strategy_bias,
            "breadth": breadth_label,
        }

    def search(self, market_state: dict, top_k: int = 5) -> list[dict]:
        """检索相似市场状态的历史记忆

        通过 tag 匹配计算相似度:
        - regime 完全匹配: +0.5
        - score_bucket 匹配: +0.25
        - bias 匹配: +0.15
        - breadth 匹配: +0.1

        Args:
            market_state: 当前市场状态
            top_k: 返回最相似的前 k 条记录

        Returns:
            list[dict]: 按相似度降序排列的历史记忆记录
        """
        try:
            tags = self.encode_market(market_state)
            recent = self._memory.get_recent(days=90)

            scored: list[tuple[float, dict]] = []
            for record in recent:
                ms = record.get("market_state", {})
                if not ms:
                    continue
                record_tags = self.encode_market(ms)
                score = self._similarity(tags, record_tags)
                if score > 0:
                    scored.append((score, record))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:top_k]]
        except Exception as e:
            logger.warning("VectorMemory.search failed: %s", e)
            return []

    def _similarity(self, a: dict, b: dict) -> float:
        """计算两组特征标签的相似度得分"""
        score = 0.0
        if a.get("regime") == b.get("regime"):
            score += 0.5
        if a.get("score_bucket") == b.get("score_bucket"):
            score += 0.25
        if a.get("bias") == b.get("bias"):
            score += 0.15
        if a.get("breadth") == b.get("breadth"):
            score += 0.1
        return score
