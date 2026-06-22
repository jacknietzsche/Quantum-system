"""Stage4 - 多Agent辩论深度分析:对Stage3 top候选进行多空辩论并生成最终信号"""

import logging

from services.debate_engine import DebateEngine
from services.skill_engine import get_skill_engine
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class Stage4Debate:
    """Stage4 辩论深度分析 - 对Stage3 top候选进行多空辩论,调整评分和信号"""

    def __init__(self, config: dict | None = None):
        self.enabled = False
        self.top_n = 5
        self.skills: list[str] = []
        self.workflow: list[dict] = []
        if config:
            self._load_config(config)

    def _load_config(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.top_n = config.get("top_n", 5)
        self.skills = config.get("skills", [])
        self.workflow = config.get("workflow", [])
        if self.enabled and self.skills:
            self._validate_skills()

    def _select_debate_candidates(self, candidates: list[dict]) -> list[dict]:
        """分歧度选股 - 优先选择 final_score 与 master_score 分歧大的候选"""
        for c in candidates:
            c["_divergence"] = abs(c.get("master_score", 50) - c.get("score", 50))
        top_by_score = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)[:10]
        top_by_score.sort(key=lambda x: x["_divergence"], reverse=True)
        selected = top_by_score[: self.top_n]
        for c in candidates:
            c["_in_debate"] = c in selected
        return candidates

    def run(self, candidates, market_regime="NEUTRAL", llm_configs=None, master_weight_factor=1.0):
        """对 Stage3 top 候选执行辩论分析,返回调整后的候选列表

        Args:
            llm_configs: 多模型配置列表,用于 LLM 多模型投票裁决
        """
        if not self.enabled or not candidates:
            for c in candidates:
                c["stage4_analyzed"] = False
            return candidates

        candidates = self._select_debate_candidates(candidates)
        debate_top = [c for c in candidates if c.get("_in_debate")]
        emit_log(
            "INFO",
            "screening",
            f"Stage4: 对 {len(debate_top)} 只股票启动辩论分析 "
            f"(skills={self.skills}, workflow={self.workflow})",
        )

        # 加载技能知识
        skill_knowledge_text = self._load_skill_knowledge()

        debate_engine = DebateEngine()
        updated = []

        for candidate in candidates:
            in_debate = candidate in debate_top
            if in_debate:
                result = self._run_single_debate(
                    debate_engine,
                    candidate,
                    market_regime,
                    skill_knowledge_text,
                    llm_configs=llm_configs,
                )
                if result:
                    self._apply_debate_result(candidate, result, master_weight_factor)
                    candidate["stage4_analyzed"] = True
            else:
                candidate["stage4_analyzed"] = False
            updated.append(candidate)

        # 按最终得分重新排序
        updated.sort(key=lambda x: x.get("score", 0), reverse=True)
        emit_log(
            "INFO",
            "screening",
            f"Stage4: 辩论完成, 已调整 {sum(1 for c in updated if c.get('stage4_analyzed'))} 只评分",
        )
        return updated

    def _validate_skills(self):
        """在配置加载时验证技能名称是否存在于注册表中"""
        try:
            engine = get_skill_engine()
            missing = engine.validate_skills(self.skills)
            if missing:
                known = list(engine.skills.keys())
                emit_log(
                    "WARNING",
                    "screening",
                    f"Stage4 配置中包含不存在的技能: {missing}, 可用技能: {known}",
                )
        except Exception as e:
            emit_log("DEBUG", "screening", f"Stage4 技能验证跳过: {e}")

    def _load_skill_knowledge(self) -> str:
        """从 SkillEngine 注入配置的技能知识"""
        if not self.skills:
            return ""
        try:
            engine = get_skill_engine()
            parts = []
            missing_names = []
            for skill_name in self.skills:
                knowledge = engine.inject_knowledge(skill_name)
                if knowledge:
                    parts.append(knowledge)
                else:
                    missing_names.append(skill_name)
            if missing_names and not parts:
                emit_log(
                    "WARNING",
                    "screening",
                    f"Stage4 所有技能均未找到: {missing_names}, 辩论将没有技能知识注入",
                )
            return "\n\n".join(parts)
        except Exception as e:
            emit_log("WARNING", "screening", f"Stage4 加载技能知识失败: {e}")
            return ""

    def _run_single_debate(
        self,
        debate_engine,
        candidate: dict,
        market_regime: str,
        skill_knowledge: str,
        llm_configs: list[dict] | None = None,
    ) -> dict | None:
        """对单只股票运行辩论引擎(规则 + 可选 LLM 多模型投票)"""
        stock_code = candidate.get("stock_code", "")
        stock_name = candidate.get("stock_name", "")
        try:
            market_context = {
                "stock_name": stock_name,
                "regime": market_regime,
                "pe": candidate.get("pe", 0),
                "roe": candidate.get("roe", 0),
                "industry": candidate.get("industry", ""),
                "pl_pct": candidate.get("change_pct", 0),
            }
            analyst_reports = self._build_analyst_reports(candidate)

            result = debate_engine.run_debate(
                stock_code=stock_code,
                analyst_reports=analyst_reports,
                market_context=market_context,
                max_rounds=2,
                llm_configs=llm_configs,
            )

            if result and result.status == "ok":
                return result.data if isinstance(result.data, dict) else None
            return None
        except Exception as e:
            emit_log("WARNING", "screening", f"Stage4 辩论失败 [{stock_code}]: {e}")
            return None

    def _build_analyst_reports(self, candidate: dict) -> list[dict]:
        """从候选股数据构建分析师报告列表"""
        reports = []
        # 基本面分析报告
        fundamentals = {
            "category": "value",
            "analysis_prompt": (
                f"ROE={candidate.get('roe', 'N/A')}, "
                f"PE={candidate.get('pe', 'N/A')}, "
                f"PB={candidate.get('pb', 'N/A')}, "
                f"营收增长={candidate.get('revenue_growth_3y', 'N/A')}%, "
                f"净利润增长={candidate.get('earnings_growth_3y', 'N/A')}%, "
                f"毛利率={candidate.get('gross_margin', 'N/A')}%, "
                f"负债率={candidate.get('debt_to_equity', 'N/A')}"
            ),
        }
        reports.append(fundamentals)

        # 趋势分析报告
        trend_report = {
            "category": "analysis",
            "analysis_prompt": (
                f"趋势={candidate.get('trend', 'N/A')}, "
                f"5日涨幅={candidate.get('change_pct_5d', 'N/A')}%, "
                f"60日涨幅={candidate.get('change_pct_60d', 'N/A')}%, "
                f"换手率={candidate.get('turnover_rate', 'N/A')}%, "
                f"量比={candidate.get('volume_ratio', 'N/A')}"
            ),
        }
        reports.append(trend_report)

        # 风险分析报告
        risk_report = {
            "category": "risk",
            "alerts": (
                f"波动率={candidate.get('volatility', 'N/A')}, "
                f"最大回撤={candidate.get('max_drawdown_60d', 'N/A')}%"
            ),
        }
        reports.append(risk_report)

        return reports

    @staticmethod
    def _apply_debate_result(candidate: dict, debate_data: dict, master_weight_factor: float = 1.0):
        """将辩论结果应用到候选股评分"""
        verdict = debate_data.get("verdict", "持有")
        confidence = debate_data.get("confidence", 0.5)
        claims = debate_data.get("claims", [])

        candidate["stage4_verdict"] = verdict
        candidate["stage4_confidence"] = round(confidence, 2)

        bull_count = sum(1 for c in claims if c.get("author") == "BullResearcher")
        bear_count = sum(1 for c in claims if c.get("author") == "BearResearcher")

        # 调整评分
        base_score = candidate.get("score", 50)
        if verdict == "买入":
            adjustment = int(15 * confidence * master_weight_factor)
            candidate["score"] = min(100, base_score + adjustment)
            if confidence >= 0.7:
                candidate["signal"] = "买入"
        elif verdict == "卖出":
            adjustment = int(20 * confidence * master_weight_factor)
            candidate["score"] = max(0, base_score - adjustment)
            candidate["signal"] = "卖出"
        else:
            # "持有" - 小幅微调
            net = bull_count - bear_count
            if net > 0:
                candidate["score"] = min(100, base_score + int(5 * master_weight_factor))
            elif net < 0:
                candidate["score"] = max(0, base_score - int(5 * master_weight_factor))

        candidate["stage4_bull_rounds"] = bull_count
        candidate["stage4_bear_rounds"] = bear_count
