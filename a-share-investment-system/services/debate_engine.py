"""多空辩论引擎 - 来源: TradingAgents-AShare"""

import uuid

from services.base import BaseService, ServiceResult
from services.memory_bank import MemoryBank
from services.quant_analyzers import QuantAnalyzers


class Claim:
    """辩论声明"""

    def __init__(
        self,
        claim_id: str,
        text: str,
        source: str,
        confidence: float,
        evidence: list[str],
        author: str,
        round_num: int,
    ):
        self.id = claim_id
        self.text = text
        self.source = source  # "bull_fundamental" | "bear_technical" | "analyst_report"
        self.confidence = confidence
        self.evidence = evidence
        self.author = author
        self.round = round_num
        self.status = "open"  # open → addressed → resolved / unresolved

    def to_dict(self) -> dict:
        return dict(self.__dict__.items())


class DebateEngine(BaseService):
    """多空辩论引擎 - 双库隔离 + 来源差异化 + 同质化门控"""

    MAX_ROUNDS = 2
    SOURCE_OVERLAP_THRESHOLD = 0.5  # 来源重合率>50%判定为低信息增量

    def __init__(self, memory_bank: MemoryBank | None = None):
        super().__init__()
        self.memory_bank = memory_bank or MemoryBank()
        self.quant = QuantAnalyzers()

    def run_debate(
        self,
        stock_code: str,
        analyst_reports: list[dict],
        market_context: dict,
        max_rounds: int = 2,
        llm_configs: list[dict] | None = None,
    ) -> ServiceResult:
        """运行完整的多空辩论"""
        try:
            claims: list[Claim] = []
            bull_history: list[str] = []
            bear_history: list[str] = []

            stock_name = market_context.get("stock_name", stock_code)
            situation = self._build_situation(
                stock_code, stock_name, analyst_reports, market_context
            )

            bull_memories = self.memory_bank.retrieve(
                {**situation, "intent": "buy"}, top_k=3, bank="bull"
            )
            bear_memories = self.memory_bank.retrieve(
                {**situation, "intent": "sell"}, top_k=3, bank="bear"
            )

            round_goals = [
                "建立最核心的正反两方声明",
                "优先攻击对手最脆弱的假设",
                "围绕时间窗口与触发条件判断交易时机是否成立",
                "围绕失败路径与失效条件检查",
            ]

            for r in range(min(max_rounds, self.MAX_ROUNDS)):
                round_num = r + 1
                goal = round_goals[min(r, len(round_goals) - 1)]

                # 多头回合
                bull_claim = self._bull_turn(
                    stock_code,
                    stock_name,
                    analyst_reports,
                    market_context,
                    claims,
                    bull_history,
                    bear_history,
                    bull_memories.data.get("memories", []),
                    goal,
                    round_num,
                )
                if bull_claim:
                    claims.append(bull_claim)
                    bull_history.append(bull_claim.text)

                bear_claim = self._bear_turn(
                    stock_code,
                    stock_name,
                    analyst_reports,
                    market_context,
                    claims,
                    bull_history,
                    bear_history,
                    bear_memories.data.get("memories", []),
                    goal,
                    round_num,
                )
                if bear_claim:
                    claims.append(bear_claim)
                    bear_history.append(bear_claim.text)

            # 同质化检测
            overlap_ratio = self._calc_source_overlap(claims)
            low_info = overlap_ratio > self.SOURCE_OVERLAP_THRESHOLD

            # 裁决
            verdict = self._judge(
                stock_code,
                stock_name,
                analyst_reports,
                market_context,
                claims,
                llm_configs=llm_configs,
            )

            if low_info:
                verdict["confidence"] = min(verdict["confidence"] * 0.7, 0.5)
                verdict["low_information_debate"] = True

            return ServiceResult.ok(
                data={
                    "verdict": verdict["verdict"],
                    "confidence": verdict["confidence"],
                    "target_price": verdict.get("target_price"),
                    "invalidation_condition": verdict.get("invalidation"),
                    "claims": [c.to_dict() for c in claims],
                    "source_overlap_ratio": round(overlap_ratio, 2),
                    "low_information_debate": low_info,
                    "bull_rounds": len(bull_history),
                    "bear_rounds": len(bear_history),
                }
            )
        except Exception as e:
            return ServiceResult.degraded(
                data={"verdict": "持有", "confidence": 0.3, "error": str(e)},
                errors=[f"DebateEngine failed, fallback to HOLD: {e}"],
            )

    def _build_situation(self, stock_code, stock_name, reports, context) -> dict:
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "regime": context.get("regime", "NEUTRAL"),
            "pe": context.get("pe", 0),
            "roe": context.get("roe", 0),
            "industry": context.get("industry", ""),
            "pl_pct": context.get("pl_pct", 0),
        }

    def _bull_turn(
        self, code, name, reports, context, claims, bull_hist, bear_hist, memories, goal, round_num
    ) -> Claim | None:
        """多头研究员 - 仅使用bull_fundamental/analyst_report来源"""
        fundamental_reports = [r for r in reports if r.get("category") in ("value", "analysis")]
        memory_texts = [m.get("situation_text", "") for m in memories if m.get("outcome_correct")]

        # Build dynamic claim from actual financial data
        roe = context.get("roe", 0)
        pe = context.get("pe", 0)
        name = context.get("stock_name", code)
        parts = []
        if roe > 15:
            parts.append(f"ROE={roe:.1f}%优秀")
        elif roe > 10:
            parts.append(f"ROE={roe:.1f}%尚可")
        if 0 < pe < 20:
            parts.append(f"PE={pe:.1f}低估")
        elif 20 <= pe < 40:
            parts.append(f"PE={pe:.1f}合理")
        claim_text = f"{name}: {','.join(parts) if parts else '基本面待观察'}。"

        # Dynamic confidence based on data quality
        bull_confidence = 0.5
        if roe > 15 and 0 < pe < 25:
            bull_confidence = 0.8
        elif roe > 10 and 0 < pe < 40:
            bull_confidence = 0.65

        evidence = []
        for r in fundamental_reports[:3]:
            key_finding = str(r.get("analysis_prompt", ""))[:120]
            if key_finding:
                evidence.append(key_finding)
        for mt in memory_texts[:2]:
            evidence.append(f"[历史成功案例] {mt[:80]}")

        return Claim(
            claim_id=f"BULL-{round_num}-{uuid.uuid4().hex[:6]}",
            text=claim_text[:200],
            source="bull_fundamental",
            confidence=bull_confidence,
            evidence=evidence,
            author="BullResearcher",
            round_num=round_num,
        )

    def _bear_turn(
        self, code, name, reports, context, claims, bull_hist, bear_hist, memories, goal, round_num
    ) -> Claim | None:
        """空头研究员 - 强制使用bear_technical来源"""
        failure_memories = [m for m in memories if not m.get("outcome_correct", True)]
        technical_reports = [r for r in reports if r.get("category") in ("analysis", "risk")]

        evidence = []
        for m in failure_memories[:2]:
            evidence.append(f"[历史失败信号] {m.get('situation_text', '')[:80]}")
        for r in technical_reports[:2]:
            risk_info = str(r.get("alerts", ""))[:100] if "alerts" in r else str(r)[:100]
            if risk_info:
                evidence.append(risk_info)

        if not failure_memories:
            evidence.append("[无历史失败记忆] 本次为空头首次分析该场景")

        # Build dynamic bear claim from actual data
        pl_pct = context.get("pl_pct", 0)
        parts = []
        if pl_pct < -5:
            parts.append(f"近期跌幅{pl_pct:.1f}%")
        if failure_memories:
            parts.append(f"历史有{len(failure_memories)}次失败信号")
        claim_text = f"{name}: {','.join(parts) if parts else '技术面存在下行风险'}。"

        # Dynamic confidence based on risk signals
        bear_confidence = 0.5
        if pl_pct < -8:
            bear_confidence = 0.75
        elif pl_pct < -3:
            bear_confidence = 0.6
        if failure_memories:
            bear_confidence = min(bear_confidence + 0.1, 0.85)

        return Claim(
            claim_id=f"BEAR-{round_num}-{uuid.uuid4().hex[:6]}",
            text=claim_text[:200],
            source="bear_technical",
            confidence=bear_confidence,
            evidence=evidence,
            author="BearResearcher",
            round_num=round_num,
        )

    def _judge(
        self, code, name, reports, context, claims, llm_configs: list[dict] | None = None
    ) -> dict:
        """研究经理裁决 - 基于声明来源多样性和一致性"""
        if not claims:
            return {"verdict": "持有", "confidence": 0.4, "reasoning": "无有效声明"}

        bull_scores = [c.confidence for c in claims if c.author == "BullResearcher"]
        bear_scores = [c.confidence for c in claims if c.author == "BearResearcher"]

        avg_bull = sum(bull_scores) / len(bull_scores) if bull_scores else 0.5
        avg_bear = sum(bear_scores) / len(bear_scores) if bear_scores else 0.5

        sources = {c.source for c in claims}
        diversity_bonus = min(0.1, len(sources) * 0.03)

        if avg_bull > avg_bear + 0.15:
            return {
                "verdict": "买入",
                "confidence": min(1.0, avg_bull + diversity_bonus),
                "reasoning": f"多头一致性高(bull={avg_bull:.2f}, bear={avg_bear:.2f})",
            }
        if avg_bear > avg_bull + 0.15:
            return {
                "verdict": "卖出",
                "confidence": min(1.0, avg_bear + diversity_bonus),
                "reasoning": f"空头信号主导(bull={avg_bull:.2f}, bear={avg_bear:.2f})",
            }
        return {
            "verdict": "持有",
            "confidence": 0.5,
            "reasoning": f"多空分歧小(bull={avg_bull:.2f}, bear={avg_bear:.2f})",
        }

    def _calc_source_overlap(self, claims: list[Claim]) -> float:
        """计算多头和空头的证据来源重合率"""
        bull_sources = set()
        bear_sources = set()
        for c in claims:
            if c.author == "BullResearcher":
                bull_sources.add(c.source)
            elif c.author == "BearResearcher":
                bear_sources.add(c.source)
        if not bull_sources or not bear_sources:
            return 0.0
        intersection = bull_sources & bear_sources
        union = bull_sources | bear_sources
        return len(intersection) / len(union) if union else 0.0
