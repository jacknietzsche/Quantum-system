"""动态管道配置引擎

根据市场状态 + 历史记忆, 动态生成全管道参数.
"""

from __future__ import annotations

import copy
import logging

from services.screening.styles import (
    Stage1Config,
    Stage2Config,
    Stage3Config,
    StyleConfig,
)
from services.screening.vector_memory import VectorMemory
from services.screening.weight_adapter import WeightAdapter
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class DynamicConfigEngine:
    """根据市场状态 + 历史记忆, 动态生成全管道参数

    输入: market_state (Stage0输出) + historical_memory
    输出: 覆盖各Stage的完整配置参数 (新对象, 不修改原配置)

    用法:
        engine = DynamicConfigEngine()
        adjusted = engine.generate(market_state, style_config)
    """

    def __init__(
        self,
        vector_memory: VectorMemory | None = None,
        weight_adapter: WeightAdapter | None = None,
    ):
        self._vm = vector_memory or VectorMemory()
        self._wa = weight_adapter or WeightAdapter()

    def generate(
        self,
        market_state: dict,
        style_config: StyleConfig,
    ) -> StyleConfig:
        """生成动态调整后的 StyleConfig

        逻辑:
        1. 从 market_state 读取 regime/composite_score/strategy_bias
        2. 从 daily_memory 查找相似市场状态的历史
        3. 如果找到相似历史且有 positive result, 日志记录 (复用待扩展)
        4. 根据市场状态动态调整各 Stage 参数
        5. Agent权重: 调用 WeightAdapter.adapt_weights()
        6. 返回新的 StyleConfig (深拷贝原配置 + 覆盖参数)

        Args:
            market_state: Stage0 输出的市场状态 (regime/composite_score/adjustment等)
            style_config: 原始风格配置

        Returns:
            StyleConfig: 动态调整后的新配置对象 (深拷贝, 不修改原对象)
        """
        # 深拷贝原配置, 避免副作用
        config = copy.deepcopy(style_config)

        try:
            regime = market_state.get("regime", "NEUTRAL")
            adjustment = market_state.get("adjustment", {})

            # 1. 根据市场状态覆盖各 Stage 参数
            self._apply_stage1_overrides(config.stage1, regime, adjustment)
            self._apply_stage2_overrides(config.stage2, regime, adjustment)
            self._apply_stage3_overrides(config.stage3, regime, adjustment)

            # 2. 查询相似历史记忆
            similar = self._query_similar_memories(market_state)
            if similar:
                emit_log(
                    "INFO",
                    "screening",
                    f"DynamicConfig: 找到 {len(similar)} 条相似市场记忆, "
                    f"最近: {similar[0].get('trade_date', 'unknown')}",
                )

            # 3. 调整 Agent 权重
            base_weights = config.stage3.weights
            adjusted_weights = self._wa.adapt_weights(base_weights, regime)
            config.stage3.weights = adjusted_weights

            emit_log(
                "INFO",
                "screening",
                f"DynamicConfig: style={style_config.name} regime={regime} "
                f"stage1_top={config.stage1.top_n} "
                f"stage2_top={config.stage2.top_n} "
                f"stage3_deep_top={config.stage3.deep_top}",
            )

        except Exception as e:
            emit_log(
                "WARNING",
                "screening",
                f"DynamicConfig.generate 失败, 使用原始配置: {e}",
            )

        return config

    def _apply_stage1_overrides(
        self,
        config: Stage1Config,
        regime: str,
        adjustment: dict,
    ) -> None:
        """根据市场状态覆盖 Stage1 参数 (in-place 修改 config)"""
        adj_top = adjustment.get("stage1_top", 1.0)
        adj_turnover = adjustment.get("turnover_min", 1.0)

        if regime in ("BEAR", "PANIC"):
            # 熊市/恐慌: 缩小候选池, 提高换手率门槛
            config.top_n = max(50, int(config.top_n * adj_top))
            if config.turnover_min > 0:
                config.turnover_min = max(0.5, config.turnover_min * adj_turnover)
            config.score_min = max(2, config.score_min)
        elif regime in ("BULL", "EUPHORIA"):
            # 牛市/狂热: 扩大候选池, 降低换手率门槛
            config.top_n = min(500, int(config.top_n * adj_top))
            if config.turnover_min > 0:
                config.turnover_min = config.turnover_min * adj_turnover
        else:
            # 震荡/分化: 保守扩大
            config.top_n = max(50, int(config.top_n * adj_top))

    def _apply_stage2_overrides(
        self,
        config: Stage2Config,
        regime: str,
        adjustment: dict,
    ) -> None:
        """根据市场状态覆盖 Stage2 参数 (in-place 修改 config)"""
        adj_top = adjustment.get("stage2_top", 1.0)

        if regime in ("BEAR", "PANIC"):
            # 熊市/恐慌: 缩小池子, 降低分数门槛让更多防御标的通过,
            # 但强制最低 ROE 和最高 PE
            config.top_n = max(10, int(config.top_n * adj_top))
            config.score_min = max(2, config.score_min - 1)
            config.min_roe = max(config.min_roe, 5.0)
            config.max_pe = min(config.max_pe, 20.0)
        elif regime in ("BULL", "EUPHORIA"):
            # 牛市/狂热: 扩大池子, 提高分数门槛精选标的
            config.top_n = min(100, int(config.top_n * adj_top))
            config.score_min = min(5, config.score_min + 1)
            config.max_pe = min(config.max_pe, 50.0)
        else:
            # 震荡/分化: 保守调整
            config.top_n = max(15, int(config.top_n * adj_top))

    def _apply_stage3_overrides(
        self,
        config: Stage3Config,
        regime: str,
        adjustment: dict,
    ) -> None:
        """根据市场状态覆盖 Stage3 参数 (in-place 修改 config)"""
        adj_top = adjustment.get("stage3_top", 1.0)

        if regime in ("BEAR", "PANIC"):
            # 熊市/恐慌: 更少进入深度分析
            config.deep_top = max(10, int(config.deep_top * adj_top))
            config.final_top = max(5, int(config.final_top * adj_top))
        elif regime in ("BULL", "EUPHORIA"):
            # 牛市/狂热: 更多候选进入深度分析
            config.deep_top = min(30, int(config.deep_top * adj_top))
            config.final_top = min(15, int(config.final_top * adj_top))
        else:
            # 震荡/分化: 适度调整
            config.deep_top = max(10, int(config.deep_top * adj_top))
            config.final_top = max(5, int(config.final_top * adj_top))

    def _query_similar_memories(
        self,
        market_state: dict,
    ) -> list[dict]:
        """从 daily_memory 查找相似市场状态的历史记录

        使用 VectorMemory 的标签匹配:
        - regime 完全匹配
        - composite_score 相差 < 0.5
        - strategy_bias 匹配

        Returns:
            list[dict]: 按相似度排序的记忆记录
        """
        try:
            return self._vm.search(market_state, top_k=3)
        except Exception as e:
            logger.debug("查询相似记忆失败: %s", e)
            return []
