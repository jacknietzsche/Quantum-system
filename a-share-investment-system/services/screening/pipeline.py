"""统一选股 Pipeline — 从 stock_screener.py 的 4 条 pipeline 合并

核心改进:
1. 4 条 pipeline 的公共模式提取为统一编排
2. 风格差异通过 StyleConfig + 阶段策略处理
3. 消除重复的 result 格式化代码
"""

from __future__ import annotations

import time as _time
from collections.abc import Callable

from services.base import ServiceResult
from services.screening.daily_memory import DailyMemory
from services.screening.dynamic_config import DynamicConfigEngine
from services.screening.stages.stage1 import stage1_quant_filter
from services.screening.stages.stage2 import stage2_fundamental_filter
from services.screening.stages.stage3 import (
    compute_master_factors,
    stage3_deep_analyze,
    stage3_master_analyze,
)
from services.screening.stages.stage4 import stage4_agent_workflow
from services.screening.styles import StyleConfig
from shared.logging import emit_log


class ScreeningPipeline:
    """统一选股 Pipeline

    用法:
        pipeline = ScreeningPipeline(style_config)
        result = pipeline.run(universe, regime, top_n)
    """

    def __init__(self, style_config: StyleConfig):
        self.config = style_config
        self.style = style_config.name

    def run(
        self,
        universe: list[dict],
        market_regime: str = "NEUTRAL",
        top_n: int = 8,
        progress_callback: Callable | None = None,
        market_data: dict | None = None,
        agent_weights: dict[str, float] | None = None,
    ) -> ServiceResult:
        """执行完整选股 Pipeline

        Args:
            universe: 股票池
            market_regime: 市场状态
            top_n: 推荐数量
            progress_callback: 进度回调
            market_data: 市场数据 (传入后自动保存到日频记忆)
            agent_weights: 动态Agent权重 (None时使用默认权重)
        """
        t0 = _time.time()

        # 动态配置引擎: 根据市场状态调整各 Stage 参数
        if market_data is not None and self._should_dynamic_config(market_data):
            try:
                engine = DynamicConfigEngine()
                dynamic_config = engine.generate(market_data, self.config)
                self.config = dynamic_config
                emit_log(
                    "INFO",
                    "screening",
                    f"[{self.style}] 动态配置已应用: "
                    f"regime={market_data.get('regime', 'N/A')} "
                    f"top_n={self.config.stage1.top_n}",
                )
            except Exception as e:
                emit_log(
                    "WARNING",
                    "screening",
                    f"[{self.style}] 动态配置引擎异常, 使用默认配置: {e}",
                )

        # Stage0: 市场感知 — 获取动态权重
        _stage0_weights = None
        try:
            from services.screening.market_perception import MarketPerception

            try:
                from llm_clients.factory import get_client_for_role

                _llm = get_client_for_role("secondary")
                if _llm is not None:
                    mp = MarketPerception(llm_client=_llm)
            except Exception:
                pass
            diagnosis = mp.diagnose()
            _stage0_weights = diagnosis.weights
            emit_log(
                "INFO",
                "screening",
                f"[{self.style}] Stage0 市场感知: {diagnosis.state} "
                f"weights={diagnosis.weights} {diagnosis.summary}",
            )
        except Exception as e:
            emit_log("DEBUG", "screening", f"[{self.style}] Stage0 skipped: {e}")

        try:
            # Stage1: 量化初筛  # noqa: ERA001
            stage1 = stage1_quant_filter(universe, self.config.stage1, self.style)
            if not stage1:
                return self._empty_result("Stage1 无通过")

            # Stage2: 四维评分 (支持市场感知动态权重)  # noqa: ERA001
            stage2 = stage2_fundamental_filter(
                stage1,
                self.config.stage2,
                self.style,
                weights=_stage0_weights,
            )
            if not stage2:
                return self._empty_result("Stage2 无通过")

            # Stage3: 深度分析 (根据风格选择策略)  # noqa: ERA001
            if self.config.stage3.master_agents:
                stage3 = stage3_master_analyze(stage2, self.config.stage3, market_regime)
            else:
                stage3 = stage3_deep_analyze(stage2, self.config.stage3, market_regime)

            if not stage3:
                return self._empty_result("Stage3 无通过")

            # Stage4: Agent 深度分析 (可选)
            stage4 = stage4_agent_workflow(stage3, self.config.stage4, self.style)

            # 格式化推荐结果
            recommendations = self._format_recommendations(stage3[:top_n])

            # 计算 Master 因子
            master_factors = compute_master_factors(stage3)

            # 构建统计信息
            pipeline_stats = self._build_stats(stage3, len(stage4), _time.time() - t0)

            emit_log(
                "INFO",
                "screening",
                f"[{self.style}] Pipeline 完成: {len(universe)} -> {len(stage1)} -> "
                f"{len(stage2)} -> {len(stage3)} -> {len(recommendations)} 推荐",
            )

            # 自动保存到日频记忆
            if market_data is not None:
                self._save_to_memory(recommendations, market_data, pipeline_stats)

            return ServiceResult.ok(
                data={
                    "total_screened": len(universe),
                    "stage1_passed": len(stage1),
                    "stage2_passed": len(stage2),
                    "filter_passed": len(stage2),
                    "stage3_recommended": len(stage3),
                    "recommendations": recommendations,
                    "style": self.style,
                    "pipeline_stats": pipeline_stats,
                    "stage4_analyses": stage4,
                    "master_factors": master_factors,
                }
            )

        except Exception as e:
            emit_log("ERROR", "screening", f"[{self.style}] Pipeline 失败: {e}")
            return ServiceResult.error(errors=[f"Pipeline failed ({self.style}): {e}"])

    def _format_recommendations(self, stage3_results: list[dict]) -> list[dict]:
        """格式化 Stage3 结果为标准推荐格式"""
        recs = []
        for i, stock in enumerate(stage3_results):
            score = stock.get("score", stock.get("_stage3_master_score", 50))
            signal = stock.get("signal", self._score_to_signal(score))
            recs.append(
                {
                    "rank": i + 1,
                    "stock_code": stock.get("stock_code", ""),
                    "stock_name": stock.get("stock_name", ""),
                    "score": round(score, 0),
                    "signal": signal,
                    "industry": stock.get("industry", ""),
                    "pe": stock.get("pe", 0),
                    "roe": stock.get("roe", 0),
                    "price": stock.get("price", stock.get("latest_price", 0)),
                    "change_pct": stock.get("change_pct", 0),
                    "turnover_rate": stock.get("turnover_rate", 0),
                    "volume_ratio": stock.get("volume_ratio", 0),
                    "confidence": round(min(score / 100, 1.0), 2),
                }
            )
        return recs

    def _score_to_signal(self, score: float) -> str:
        if score >= 70:
            return "买入"
        if score >= 50:
            return "持有"
        return "观望"

    def _build_stats(self, stage3: list[dict], stage4_count: int, elapsed: float) -> dict:
        sd = {}
        for r in stage3:
            sig = r.get("signal", "")
            sd[sig] = sd.get(sig, 0) + 1
        avg = round(sum(r.get("score", 0) for r in stage3) / len(stage3), 1) if stage3 else 0
        return {
            "stage3_total": len(stage3),
            "stage3_pass": len([r for r in stage3 if r.get("score", 0) >= 60]),
            "stage3_errors": 0,
            "avg_score": avg,
            "signal_distribution": sd,
            "stage4_count": stage4_count,
            "pipeline_time_s": round(elapsed, 1),
        }

    def _save_to_memory(
        self,
        recommendations: list[dict],
        market_data: dict,
        pipeline_stats: dict,
    ) -> None:
        """将推荐结果保存到日频记忆"""
        try:
            picks = []
            for r in recommendations:
                picks.append(
                    {
                        "stock_code": r.get("stock_code", ""),
                        "stock_name": r.get("stock_name", ""),
                        "agent_name": self.style,
                        "score": r.get("score", 50),
                        "signal": r.get("signal", "neutral"),
                        "price": r.get("price", 0),
                        "change_pct": r.get("change_pct", 0),
                        "pe": r.get("pe", 0),
                        "roe": r.get("roe", 0),
                        "industry": r.get("industry", ""),
                    }
                )

            memory = DailyMemory()
            memory.save_daily(
                market_state={
                    "regime": market_data.get("regime", "NEUTRAL"),
                    "style": self.style,
                    "pipeline_stats": pipeline_stats,
                    "breadth": market_data.get("breadth", {}),
                    "indices": market_data.get("indices", {}),
                },
                picks=picks,
            )
        except Exception as e:
            emit_log("WARNING", "screening", f"保存日频记忆失败: {e}")

    @staticmethod
    def _should_dynamic_config(market_data: dict) -> bool:
        """判断是否应该触发动态配置

        当 market_data 包含 regime 字段时才触发, 否则保持默认配置。
        """
        return bool(market_data.get("regime"))

    def _empty_result(self, reason: str) -> ServiceResult:
        emit_log("WARNING", "screening", f"[{self.style}] {reason}")
        return ServiceResult.ok(
            data={
                "total_screened": 0,
                "stage1_passed": 0,
                "stage2_passed": 0,
                "stage3_recommended": 0,
                "filter_passed": 0,
                "recommendations": [],
                "style": self.style,
                "pipeline_stats": {
                    "stage3_total": 0,
                    "stage3_pass": 0,
                    "stage3_errors": 0,
                    "avg_score": 0,
                    "signal_distribution": {},
                    "stage4_count": 0,
                },
            }
        )
