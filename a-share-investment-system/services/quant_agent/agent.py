"""QuantAgent — AI量化分析师核心

每日自主运行思考循环: 感知→判断→行动→决策→复盘
所有量化能力通过 ToolRegistry 调用, 编排权和决策权交给AI。
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime

from services.quant_agent.memory import MemorySystem
from services.quant_agent.safety import SafetyBoundary
from services.quant_agent.schemas import (
    DecisionReport,
    MarketDiagnosis,
    QuantAgentState,
    Reflection,
    StockPick,
    StrategyPlan,
    ThoughtStep,
)
from services.quant_agent.tools import ToolRegistry, default_tool_registry

logger = logging.getLogger(__name__)


class QuantAgent:
    """AI量化分析师

    用法:
        agent = QuantAgent()
        report = agent.daily_cycle()  # 同步模式
        async for event in agent.daily_cycle_stream(): ...  # SSE流式
    """

    def __init__(
        self,
        llm_client=None,
        tool_registry: ToolRegistry | None = None,
        memory: MemorySystem | None = None,
        safety: SafetyBoundary | None = None,
    ):
        self.llm = llm_client
        self.tools = tool_registry or default_tool_registry()
        self.memory = memory or MemorySystem()
        self.safety = safety or SafetyBoundary()
        self.state = QuantAgentState()

        # 如果没有显式传入LLM, 尝试自动获取
        if self.llm is None:
            try:
                from llm_clients.factory import get_client_for_role

                self.llm = get_client_for_role("primary")
                if self.llm is None:
                    self.llm = get_client_for_role("secondary")
            except Exception:
                pass

    # ── 主入口 ──

    def daily_cycle(self, force: bool = False) -> DecisionReport:
        """每日自主循环 (同步模式)"""
        self.state.status = "thinking"
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            # Phase 1: 感知
            perception = self._perceive(force)
            self._add_thought("perceive", "市场感知", perception.get("summary", ""), perception)

            # Phase 2: 判断
            strategy = self._judge(perception)
            self._add_thought("judge", "策略判断", f"选择{strategy.style}策略", strategy.__dict__)

            # Phase 3: 行动
            analysis = self._act(strategy)
            self._add_thought(
                "act",
                "量化分析",
                "筛选→评分→深度分析完成",
                {"counts": {k: len(v) if isinstance(v, list) else v for k, v in analysis.items()}},
            )

            # Phase 4: 决策
            decision = self._decide(strategy, analysis)
            decision = self.safety.enforce(decision)
            decision.date = today
            self.state.final_picks = decision.picks
            self._add_thought(
                "decide",
                "最终决策",
                f"推荐{len(decision.picks)}只标的",
                {"picks": [p.stock_code for p in decision.picks]},
            )

            # 保存记忆
            weights = perception.get("weights", {})
            self.memory.save_decision(
                today,
                perception.get("state", "SHOCK"),
                weights,
                [p.__dict__ for p in decision.picks],
                decision.portfolio_summary,
            )

            # Phase 5: 复盘 (不阻塞)
            try:
                reflection = self._reflect(decision)
                self.memory.save_reflection(
                    today,
                    reflection.summary,
                    reflection.insights,
                    reflection.mistakes,
                    reflection.improvements,
                )
            except Exception as e:
                logger.warning("[QuantAgent] 复盘失败: %s", e)

            self.state.status = "done"
            return decision

        except Exception as e:
            self.state.status = "error"
            self.state.error = str(e)
            logger.error("[QuantAgent] 决策循环失败: %s", e)
            raise

    async def daily_cycle_stream(self) -> AsyncGenerator[dict, None]:
        """每日自主循环 (SSE流式模式)"""
        self.state.status = "thinking"
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            # Phase 1
            yield {"type": "phase", "phase": "perceive", "title": "市场感知"}
            perception = self._perceive()
            yield {
                "type": "thought",
                "phase": "perceive",
                "content": perception.get("summary", ""),
                "data": {"state": perception.get("state"), "weights": perception.get("weights")},
            }
            self._add_thought("perceive", "市场感知", perception.get("summary", ""), perception)

            # Phase 2
            yield {"type": "phase", "phase": "judge", "title": "策略判断"}
            strategy = self._judge(perception)
            yield {
                "type": "thought",
                "phase": "judge",
                "content": strategy.reasoning,
                "data": {"style": strategy.style, "weights": strategy.factor_weights},
            }
            self._add_thought("judge", "策略判断", strategy.reasoning, strategy.__dict__)

            # Phase 3
            yield {"type": "phase", "phase": "act", "title": "量化分析"}
            yield {
                "type": "tool_call",
                "tool": "screen:active",
                "params": {"style": strategy.style},
            }
            analysis = self._act(strategy)
            yield {
                "type": "tool_result",
                "tool": "factor:score",
                "summary": f"评分完成, 候选{analysis.get('scored_count', 0)}只",
            }
            self._add_thought("act", "量化分析", "筛选+评分完成", analysis)

            # Phase 4
            yield {"type": "phase", "phase": "decide", "title": "最终决策"}
            decision = self._decide(strategy, analysis)
            decision = self.safety.enforce(decision)
            decision.date = today
            self.state.final_picks = decision.picks
            yield {
                "type": "final_recommendation",
                "picks": [p.__dict__ for p in decision.picks],
                "summary": decision.portfolio_summary,
            }
            self._add_thought("decide", "最终决策", f"推荐{len(decision.picks)}只", {})

            # 保存
            weights = perception.get("weights", {})
            self.memory.save_decision(
                today,
                perception.get("state", "SHOCK"),
                weights,
                [p.__dict__ for p in decision.picks],
                decision.portfolio_summary,
            )

            # Phase 5
            yield {"type": "phase", "phase": "reflect", "title": "AI复盘"}
            reflection = self._reflect(decision)
            self.memory.save_reflection(
                today,
                reflection.summary,
                reflection.insights,
                reflection.mistakes,
                reflection.improvements,
            )
            yield {
                "type": "reflection",
                "summary": reflection.summary[:200],
                "insights": reflection.insights[:3],
            }

            yield {"type": "done", "pick_count": len(decision.picks)}
            self.state.status = "done"

        except Exception as e:
            self.state.status = "error"
            self.state.error = str(e)
            yield {"type": "error", "message": str(e)}

    # ── 5个阶段 ──

    def _perceive(self, force_refresh: bool = False) -> dict:
        """Phase 1: 感知市场"""
        try:
            diagnosis = self.tools.call("market:diagnose", force_refresh=force_refresh)
            self.state.diagnosis = MarketDiagnosis(
                state=diagnosis.state,
                confidence=diagnosis.confidence,
                weights=diagnosis.weights,
                summary=diagnosis.summary,
                details=diagnosis.details,
            )
            return {
                "state": diagnosis.state,
                "confidence": diagnosis.confidence,
                "weights": diagnosis.weights,
                "summary": diagnosis.summary,
                "details": diagnosis.details,
            }
        except Exception as e:
            logger.warning("[QuantAgent] perceive fallback: %s", e)
            return {
                "state": "SHOCK",
                "confidence": 0.5,
                "weights": {"trend": 0.25, "capital": 0.25, "fundamental": 0.25, "defensive": 0.25},
                "summary": "市场诊断不可用",
                "details": {},
            }

    def _judge(self, perception: dict) -> StrategyPlan:
        """Phase 2: AI判断策略"""
        weights = perception.get("weights", {})
        state = perception.get("state", "SHOCK")

        if self.llm:
            try:
                prompt = self._judge_prompt(perception)
                text = self.llm.invoke(prompt, temperature=0.4, max_tokens=500)
                if text:
                    result = json.loads(self._clean_json(text))
                    return StrategyPlan(
                        style=result.get("style", "hybrid"),
                        factor_weights=result.get("factor_weights", weights),
                        max_positions=result.get("max_positions", 8),
                        risk_budget=result.get("risk_budget", 0.15),
                        reasoning=result.get("reasoning", ""),
                    )
            except Exception as e:
                logger.warning("[QuantAgent] LLM judge failed, fallback: %s", e)

        style_map = {
            "BULL": "momentum",
            "BEAR": "defensive",
            "SHOCK": "hybrid",
            "VOLATILE": "hybrid",
        }
        return StrategyPlan(
            style=style_map.get(state, "hybrid"),
            factor_weights=weights,
            reasoning=f"规则降级: 市场{state}, 适用{style_map.get(state, 'hybrid')}策略",
        )

    def _act(self, strategy: StrategyPlan) -> dict:
        """Phase 3: AI调用的量化工具"""
        results = {}

        # 1. 行为活性筛选
        active = self.tools.call("screen:active", style=strategy.style, top_n=200)
        results["active_count"] = len(active)

        # 2. 四维评分
        if active:
            scored = self.tools.call(
                "factor:score", stocks=active, style=strategy.style, weights=strategy.factor_weights
            )
            results["scored_count"] = len(scored)
            results["top_scores"] = [
                {"code": s.get("stock_code", ""), "score": s.get("_stage2_score", 0)}
                for s in scored[:10]
            ]

            # 3. AI基本面分析 (top 30)
            top30 = scored[:30]
            try:
                fundamentals = self.tools.call("fundamental:analyze", stocks=top30)
                results["fundamental_count"] = len(fundamentals) if fundamentals else 0
            except Exception as e:
                logger.debug("[QuantAgent] fundamental:analyze: %s", e)

        return results

    def _decide(self, strategy: StrategyPlan, analysis: dict) -> DecisionReport:
        """Phase 4: AI做出最终决策"""
        scored = analysis.get("top_scores", [])

        # LLM模式
        if self.llm and scored:
            try:
                prompt = self._decide_prompt(strategy, analysis)
                text = self.llm.invoke(prompt, temperature=0.3, max_tokens=1000)
                if text:
                    result = json.loads(self._clean_json(text))
                    picks_data = result.get("picks", [])
                    picks = [
                        StockPick(
                            rank=i + 1,
                            stock_code=p.get("code", ""),
                            stock_name=p.get("name", ""),
                            score=float(p.get("score", 50)),
                            weight=float(p.get("weight", 0.1)),
                            reason=p.get("reason", ""),
                            stop_loss=float(p.get("stop_loss", -0.05)),
                            take_profit=float(p.get("take_profit", 0.1)),
                            risk=p.get("risk", ""),
                            signal=p.get("signal", "观望"),
                        )
                        for i, p in enumerate(picks_data[:8])
                    ]
                    if picks:
                        return DecisionReport(
                            picks=picks,
                            portfolio_summary=result.get("summary", ""),
                            risk_warnings=result.get("warnings", []),
                        )
            except Exception as e:
                logger.warning("[QuantAgent] LLM decide failed: %s", e)

        # 规则降级
        picks = []
        for i, s in enumerate(scored[:8]):
            picks.append(
                StockPick(
                    rank=i + 1,
                    stock_code=s.get("code", ""),
                    score=float(s.get("score", 0)),
                    weight=max(0.02, 0.16 - i * 0.02),
                    reason=f"四维评分{s.get('score', 0):.1f}分",
                    stop_loss=-0.05,
                    take_profit=0.10,
                    signal="买入" if s.get("score", 0) >= 7 else "持有",
                )
            )
        return DecisionReport(
            picks=picks,
            portfolio_summary=f"基于{strategy.style}策略, 推荐{len(picks)}只标的",
            risk_warnings=[],
        )

    def _reflect(self, decision: DecisionReport) -> Reflection:
        """Phase 5: AI复盘"""
        yesterday = self.memory.get_yesterday_decision()
        if yesterday:
            prev_count = len(yesterday.get("picks", []))
            insights = [f"昨日推荐{prev_count}只, 今日推荐{len(decision.picks)}只"]
            mistakes = []
            improvements = ["持续跟踪推荐标的表现"]
        else:
            insights = ["首个交易日"]
            mistakes = []
            improvements = []

        return Reflection(
            date=datetime.now().strftime("%Y-%m-%d"),
            summary=f"完成当日决策循环, 产出{len(decision.picks)}只推荐",
            insights=insights,
            mistakes=mistakes,
            improvements=improvements,
        )

    # ── 辅助 ──

    def _add_thought(self, phase: str, title: str, summary: str, data: dict):
        ts = datetime.now().isoformat()
        thought = ThoughtStep(
            phase=phase, title=title, content=summary, summary=summary, data=data, timestamp=ts
        )
        self.state.thoughts.append(thought)
        with contextlib.suppress(Exception):
            self.memory.log_thought(datetime.now().strftime("%Y-%m-%d"), phase, title, summary)

    def get_state(self) -> QuantAgentState:
        return self.state

    @staticmethod
    def _judge_prompt(perception: dict) -> str:
        """构建策略判断提示词"""
        return f"""你是A股量化策略师。基于今日市场诊断, 制定选股策略。

市场状态: {perception.get("state", "SHOCK")}
置信度: {perception.get("confidence", 0.5)}
动态权重: {perception.get("weights", {})}
市场总结: {perception.get("summary", "")}

请输出JSON格式策略:
{{{{
  "style": "hybrid/momentum/defensive/limit_up",
  "factor_weights": {{"trend": 0.x, "capital": 0.x, "fundamental": 0.x, "defensive": 0.x}},
  "max_positions": 8,
  "risk_budget": 0.15,
  "reasoning": "策略逻辑简述"
}}}}"""

    @staticmethod
    def _decide_prompt(strategy: StrategyPlan, analysis: dict) -> str:
        """构建最终决策提示词"""
        top_scores = analysis.get("top_scores", [])
        codes_str = ", ".join(
            f"{s.get('code', '')}={s.get('score', 0):.1f}" for s in top_scores[:15]
        )

        return f"""你是A股投资经理。基于以下信息, 从候选池中选出最多8只推荐。

策略: {strategy.style}
权重: {strategy.factor_weights}
候选池评分: {codes_str}

输出JSON格式:
{{{{
  "picks": [
    {{{{"code": "000001", "name": "...", "score": 85, "weight": 0.15, "reason": "推荐理由", "stop_loss": -0.05, "take_profit": 0.10, "risk": "主要风险", "signal": "买入"}}}}
  ],
  "summary": "整体策略说明",
  "warnings": ["风险提示1"]
}}}}
要求: 最多选8只, 每只给出具体理由。"""

    @staticmethod
    def _clean_json(text: str) -> str:
        """清理LLM输出中的markdown标记"""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        return text.strip()
