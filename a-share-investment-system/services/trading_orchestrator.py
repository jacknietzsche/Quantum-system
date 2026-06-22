"""TradingStrategyOrchestrator - AI 深度分析编排器 with multi-model ensemble + LLM fallback"""

import logging
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from services.agents.decision_agent import DecisionAgent
from services.agents.portfolio_agent import PortfolioAgent
from services.agents.stock_agent import StockAgent
from services.llm_router import get_router
from shared.config import Config
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class TradingStrategyOrchestrator:
    """编排 StockAgent(Primary+Ensemble) → PortfolioAgent → DecisionAgent 完整流程

    多模型 Ensemble:
    - 主模型(第1个)分析全部候选
    - 其余模型分析 Top-K 候选做交叉验证
    - 聚合: 评分取均值, 信号取多数
    """

    def __init__(
        self,
        style: str = "hybrid",
        portfolio_holdings: dict | None = None,
        progress_callback=None,
        abort_check=None,
    ):
        self.style = style
        self.portfolio_holdings = portfolio_holdings or {}
        self.progress_callback = progress_callback
        self._abort_check = abort_check or (lambda: False)
        self.llm_configs = self._resolve_llm_configs()
        self.ensemble_top_k = Config().get("screening.deep_analysis.ensemble_top_k", 8)
        self._router = get_router()

    def _progress(self, pct: int, msg: str = ""):
        self.progress_callback(pct, msg)

    @staticmethod
    def resolve_multi_llm_configs() -> list[dict]:
        """从 config.yaml 解析多模型配置列表 (供外部复用, 如 Stage4 辩论)"""
        cfg = Config()
        providers = cfg.get("llm_providers", {})
        model_specs = cfg.get("screening.deep_analysis.models", [])
        if not model_specs:
            single = cfg.get("screening.deep_analysis.model", "deepseek.com:deepseek-v4-pro")
            model_specs = [single]

        def _build(mspec: str) -> dict | None:
            if not mspec or ":" not in mspec:
                return None
            provider, model = mspec.split(":", 1)
            pcfg = providers.get(provider, {})
            api_key = pcfg.get("api_key", "")
            if not api_key:
                return None
            base_url = pcfg.get("base_url", f"https://api.{provider}/v1")
            return {
                "base_url": base_url.rstrip("/"),
                "api_key": api_key,
                "model": model,
                "provider": provider,
            }

        return [_build(m) for m in model_specs if _build(m) is not None]

    def _resolve_llm_configs(self) -> list[dict]:
        """解析多模型 LLM 配置 (主模型 + 交叉验证模型)"""
        configs = self.resolve_multi_llm_configs()
        if not configs:
            # 兜底: 用 Router 获取可用 provider
            available = self._router.get_available_providers("standard")
            if available:
                provider, model = available[0]
                cfg = Config()
                api_key = cfg.get_api_key(provider)
                base_url = cfg.get_base_url(provider)
                if api_key:
                    configs.append(
                        {
                            "base_url": base_url.rstrip("/"),
                            "api_key": api_key,
                            "model": model,
                            "provider": provider,
                        }
                    )
        return configs

    def run(self, candidates: list[dict], quant_anchors: bool = False) -> dict:
        """执行完整分析流程 (sync) - 多模型 Ensemble 模式

        Args:
            candidates: 候选股票列表
            quant_anchors: 是否启用量化锚定模式
        """
        if len(candidates) < 3:
            self._progress(35, "候选股不足, 跳过 AI 分析")
            return self._generate_simple_plan(candidates)

        if not self.llm_configs:
            return self._generate_simple_plan(candidates)

        primary_cfg = self.llm_configs[0]
        ensemble_cfgs = self.llm_configs[1:]
        total = len(candidates)

        # ── Phase 1: 主模型分析全部候选 ──
        self._progress(35, f"个股分析中 (主模型: {primary_cfg.get('model', '?')})...")
        emit_log(
            "INFO",
            "screening",
            f"Stage3: {total}只, 主模型={primary_cfg.get('model', '?')}, "
            f"ensemble模型={len(ensemble_cfgs)}个",
        )

        stock_opinions = self._run_stock_agent_batch(primary_cfg, candidates, quant_anchors)

        # ── Phase 2: Ensemble 模型交叉验证 Top-K ──
        ek = min(self.ensemble_top_k or 8, total)
        if ensemble_cfgs and ek >= 3:
            scored = sorted(
                range(total),
                key=lambda i: stock_opinions[i].get("overall_score", 0) if stock_opinions[i] else 0,
                reverse=True,
            )
            top_indices = scored[:ek]

            ensemble_map = defaultdict(list)
            for idx in top_indices:
                code = candidates[idx].get("stock_code", "")
                if stock_opinions[idx]:
                    ensemble_map[code].append(stock_opinions[idx])

            for ei, ecfg in enumerate(ensemble_cfgs):
                mn = ecfg.get("model", "?")
                self._progress(
                    35 + int((ei + 1) / (len(ensemble_cfgs) + 1) * 15),
                    f"交叉验证 ({mn})...",
                )
                extra = self._run_stock_agent_batch(
                    ecfg, [candidates[i] for i in top_indices], quant_anchors
                )
                for i, idx in enumerate(top_indices):
                    code = candidates[idx].get("stock_code", "")
                    if extra[i] and not extra[i].get("error"):
                        ensemble_map[code].append(extra[i])

            # 聚合多模型意见
            for code, opinions in ensemble_map.items():
                scores = [o.get("overall_score", 50) for o in opinions if not o.get("error")]
                signals = [o.get("signal", "观望") for o in opinions if not o.get("error")]
                if not scores:
                    continue
                avg_score = round(sum(scores) / len(scores))
                sig_counts = Counter(signals)
                majority_sig = sig_counts.most_common(1)[0][0]
                best = max(
                    (o for o in opinions if not o.get("error")),
                    key=lambda o: o.get("overall_score", 0),
                    default=opinions[0],
                )
                for idx in top_indices:
                    if candidates[idx].get("stock_code") == code:
                        stock_opinions[idx] = {
                            **best,
                            "overall_score": avg_score,
                            "signal": majority_sig,
                            "ensemble_count": len(opinions),
                            "ensemble_agreement": round(
                                sig_counts.most_common(1)[0][1] / len(signals) * 100
                            ),
                        }
                        break

        # ── 统计 ──
        success_count = sum(1 for o in stock_opinions if o and not o.get("error"))
        fail_count = sum(1 for o in stock_opinions if o and o.get("error"))
        emit_log(
            "INFO",
            "screening",
            f"Stage3: {len(stock_opinions)}只, {success_count}成功/{fail_count}失败",
        )

        if fail_count > 0 and len(self.llm_configs) > 1:
            fallback_cfg = self.llm_configs[-1]
            if fallback_cfg.get("model") != primary_cfg.get("model"):
                failed_idx = [i for i, o in enumerate(stock_opinions) if o and o.get("error")]
                emit_log(
                    "INFO",
                    "screening",
                    f"降级: 用{fallback_cfg.get('model', '?')}重试{fail_count}只失败...",
                )
                retry = self._run_stock_agent_batch(
                    fallback_cfg, [candidates[i] for i in failed_idx], quant_anchors
                )
                for i, idx in enumerate(failed_idx):
                    if retry[i] and not retry[i].get("error"):
                        stock_opinions[idx] = retry[i]
                        emit_log(
                            "INFO",
                            "screening",
                            f"降级重试成功: {candidates[idx].get('stock_code', '')}",
                        )

        # ── PortfolioAgent + DecisionAgent (使用主模型) ──
        self._progress(60, "组合分析中 (PortfolioAgent)...")
        try:
            portfolio_assessment = PortfolioAgent(primary_cfg).analyze(
                stock_opinions, self.portfolio_holdings or {}
            )
        except Exception as e:
            logger.warning("PortfolioAgent failed: %s", e)
            portfolio_assessment = {"portfolio_risk_score": 5, "warnings": [str(e)]}

        self._progress(80, "生成交易计划 (DecisionAgent)...")
        try:
            trading_plan = DecisionAgent(primary_cfg).decide(
                stock_opinions, portfolio_assessment, self.portfolio_holdings or {}
            )
        except Exception as e:
            logger.warning("DecisionAgent failed: %s", e)
            trading_plan = None

        self._progress(95, "交易计划完成")
        return {
            "style": self.style,
            "stock_opinions": stock_opinions,
            "portfolio_assessment": portfolio_assessment,
            "trading_plan": trading_plan.to_dict()
            if trading_plan and hasattr(trading_plan, "to_dict")
            else {},
        }

    def _run_stock_agent_batch(
        self, llm_config: dict, stocks: list[dict], quant_anchors: bool = False
    ) -> list[dict]:
        """使用指定模型批量运行 StockAgent,返回 opinions 列表"""
        cfg = Config()
        max_workers = min(len(stocks), cfg.get("screening.deep_analysis.parallel_limit", 3))
        total = len(stocks)
        stock_agent = StockAgent(llm_config)

        sc = cfg.get(f"screening.styles.{self.style}.stage3", {})
        max_adjustment = sc.get("max_adjustment", 15)
        force_dissent = sc.get("force_dissent_review", False)

        def _run(idx, stock):
            if quant_anchors:
                stock_agent.quant_anchor = {
                    "master_score": stock.get("master_score", 50),
                    "admission_tags": stock.get("admission_tags", []),
                    "quant_report": stock.get("quant_report", {}),
                }
                stock_agent.max_adjustment = max_adjustment
                stock_agent.force_dissent = force_dissent
            return idx, stock_agent.analyze(stock)

        opinions = [None] * total
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            pending = {executor.submit(_run, i, s): i for i, s in enumerate(stocks)}
            LLM_TIMEOUT = 120
            while pending:
                if self._abort_check():
                    for f in pending:
                        f.cancel()
                    break
                done, pending = wait(pending, timeout=LLM_TIMEOUT, return_when=FIRST_COMPLETED)
                if not done:
                    for f in pending:
                        f.cancel()
                    break
                for future in done:
                    idx, result = future.result()
                    if isinstance(result, dict) and result.get("error"):
                        opinions[idx] = {
                            "stock_code": stocks[idx].get("stock_code"),
                            "stock_name": stocks[idx].get("stock_name"),
                            "overall_score": 40,
                            "signal": "观望",
                            "error": result["error"],
                        }
                    else:
                        opinions[idx] = result

        return opinions

    def _generate_simple_plan(self, candidates: list[dict]) -> dict:
        """候选股太少时生成简单计划"""
        opinions = []
        for s in candidates:
            opinions.append(
                {
                    "stock_code": s.get("stock_code"),
                    "stock_name": s.get("stock_name"),
                    "overall_score": s.get("score", 50),
                    "signal": "观望",
                }
            )
        return {
            "style": self.style,
            "stock_opinions": opinions,
            "portfolio_assessment": {
                "portfolio_risk_score": 3,
                "warnings": ["候选股不足3只, 跳过AI分析"],
            },
            "trading_plan": {
                "market_assessment": {"regime": "不确定", "risk_level": "低"},
                "execution_plan": {"immediate_summary": "候选池不足, 暂不操作"},
                "risk_management": {"circuit_breaker": "N/A"},
            },
        }
