"""兼容层 — 保持 StockScreener 公共 API 不变

StockScreener 是旧代码的入口，内部委托给 ScreeningPipeline。
所有外部调用方 (main.py, api/routes/screening.py) 无需修改。
"""

from __future__ import annotations

from collections.abc import Callable

from services.base import BaseService, ServiceResult
from services.screening.pipeline import ScreeningPipeline
from services.screening.styles import load_style_config
from shared.logging import emit_log

VALID_STYLES = {"hybrid", "limit_up", "momentum", "value", "category"}


def classify_stock_category(code: str, name: str = "") -> str:
    """根据股票代码/名称判断所属分类"""
    if name.startswith(("68",)):
        return "tech"
    if name.startswith(("银行",)):
        return "finance"
    # ... 其他分类逻辑
    return "general"


class StockScreener(BaseService):
    """选股器 — 兼容旧 API，内部委托给 ScreeningPipeline"""

    def __init__(
        self,
        style: str = "hybrid",
        factor_farm=None,
        config=None,
    ):
        super().__init__()
        self.style = style if style in VALID_STYLES else "hybrid"
        self._factor_farm = factor_farm
        self._config_obj = config
        self._portfolio_holdings = {}
        self._progress_callback = None

        # 加载风格配置
        self._style_config = load_style_config(self.style, config)

        # 兼容旧属性 (某些外部代码可能直接访问)  # noqa: ERA001
        self._expose_legacy_attrs()

    def _expose_legacy_attrs(self):
        """暴露旧属性名以保持兼容"""
        sc = self._style_config
        self.stage1_top_n = sc.stage1.top_n
        self.stage1_score_min = sc.stage1.score_min
        self.stage1_turnover_min = sc.stage1.turnover_min
        self.stage1_market_cap_min = sc.stage1.market_cap_min
        self.stage1_volatility_max = sc.stage1.volatility_max
        self.stage2_top_n = sc.stage2.top_n
        self.stage2_score_min = sc.stage2.score_min
        self.stage3_deep_top = sc.stage3.deep_top
        self.stage3_final_top = sc.stage3.final_top
        self.stage4_enabled = sc.stage4.enabled
        self.stage4_top_n = sc.stage4.top_n

    @property
    def factor_farm(self):
        if self._factor_farm is None:
            from services.factor_farm import FactorFarm

            self._factor_farm = FactorFarm()
        return self._factor_farm

    def run(
        self,
        stock_universe: list[dict] | None = None,
        market_regime: str = "NEUTRAL",
        top_n: int | None = None,
        portfolio_holdings: dict | None = None,
        candidates: list[dict] | None = None,
        progress_callback: Callable | None = None,
    ) -> ServiceResult:
        """执行多选股 — 委托给 ScreeningPipeline"""
        try:
            self._portfolio_holdings = portfolio_holdings or {}
            self._progress_callback = progress_callback

            # 加载股票池
            if stock_universe is None:
                emit_log("INFO", "screening", f"[{self.style}] 加载股票池...")
                stock_universe = self._load_universe()

            # 空股票池直接返回空结果，避免进入 LLM/网络调用
            if not stock_universe:
                return ServiceResult.ok(
                    data={
                        "total_screened": 0,
                        "stage1_passed": 0,
                        "stage2_passed": 0,
                        "stage3_recommended": 0,
                        "filter_passed": 0,
                        "recommendations": [],
                        "style": self.style,
                        "pipeline_stats": self._empty_pipeline_stats(),
                    }
                )

            # 如果直接传入 candidates，跳过 Stage1/2
            if candidates is not None:
                pipeline = ScreeningPipeline(self._style_config)
                # 直接从 Stage3 开始
                from services.screening.stages.stage3 import stage3_deep_analyze

                stage3 = stage3_deep_analyze(candidates, self._style_config.stage3, market_regime)
                from services.screening.stages.stage3 import compute_master_factors

                recs = pipeline._format_recommendations(stage3[: top_n or self.stage3_final_top])
                result = ServiceResult.ok(
                    data={
                        "total_screened": len(candidates),
                        "stage1_passed": len(candidates),
                        "stage2_passed": len(candidates),
                        "stage3_recommended": len(stage3),
                        "filter_passed": len(candidates),
                        "recommendations": recs,
                        "style": self.style,
                        "pipeline_stats": self._empty_pipeline_stats(),
                        "master_factors": compute_master_factors(stage3),
                    }
                )
            else:
                # 正常 Pipeline 流程
                pipeline = ScreeningPipeline(self._style_config)
                result = pipeline.run(
                    stock_universe,
                    market_regime,
                    top_n or self.stage3_final_top,
                    progress_callback,
                )

            # Post-pipeline: 持仓上下文 + 信号持久化
            if result.status == "ok" and result.data:
                recs = result.data.get("recommendations", [])
                if self._portfolio_holdings:
                    recs = self._apply_portfolio_context(recs, self._portfolio_holdings)
                    result.data["recommendations"] = recs
                self._save_style_signals(recs)

            return result
        except Exception as e:
            return ServiceResult.error(errors=[f"Screening failed ({self.style}): {e}"])

    def run_by_category(
        self,
        stock_universe: list[dict] | None = None,
        market_regime: str = "NEUTRAL",
        top_n_per_category: int = 5,
        portfolio_holdings: dict | None = None,
    ) -> ServiceResult:
        """按分类选股"""
        # ... 保持原有逻辑
        try:
            if stock_universe is None:
                stock_universe = self._load_universe()

            # 按行业/概念分类
            categories = {}
            for stock in stock_universe:
                cat = stock.get("industry", "其他")
                categories.setdefault(cat, []).append(stock)

            all_recs = []
            category_results = {}
            for cat, stocks in categories.items():
                pipeline = ScreeningPipeline(self._style_config)
                result = pipeline.run(stocks, market_regime, top_n_per_category)
                if result.status == "ok" and result.data:
                    recs = result.data.get("recommendations", [])
                    category_results[cat] = {
                        "category_name": cat,
                        "recommendations": recs,
                        "count": len(recs),
                    }
                    all_recs.extend(recs)

            all_recs.sort(key=lambda x: x.get("score", 0), reverse=True)
            return ServiceResult.ok(
                data={
                    "total_screened": len(stock_universe),
                    "categories": category_results,
                    "recommendations": all_recs,
                    "style": self.style,
                    "top_n_per_category": top_n_per_category,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"Category screening failed ({self.style}): {e}"])

    def _load_universe(self) -> list[dict]:
        """加载全A股股票池"""
        from shared.logging import emit_log

        universe = []
        session = None
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            count = session.query(StockInfo).filter(StockInfo.latest_price > 0).count()
            if count == 0:
                session.close()
                emit_log("WARNING", "screening", "数据库为空,触发自动填充...")
                from services.data_initializer import DataInitializer

                di = DataInitializer()
                di.refresh_stock_list()
                session = get_session()

            rows = session.query(StockInfo).filter(StockInfo.latest_price > 0).all()
            for row in rows:
                universe.append(
                    {
                        "stock_code": row.stock_code,
                        "stock_name": row.stock_name or "",
                        "latest_price": float(row.latest_price or 0),
                        "market_cap": float(row.total_market_cap or 0),
                        "turnover_rate": float(row.turnover_rate or 0),
                        "pe": float(row.pe_ratio or 0),
                        "pb": float(row.pb_ratio or 0),
                        "roe": float(row.roe or 0),
                        "industry": row.industry or "",
                        "change_pct": float(row.change_pct or 0),
                        "amount": float(row.amount or 0),
                        "volume": float(row.volume or 0),
                        "ma5": float(row.ma5 or 0),
                        "ma10": float(row.ma10 or 0),
                        "ma20": float(row.ma20 or 0),
                        "ma60": float(row.ma60 or 0),
                        "rsi_14": float(row.rsi_14 or 0),
                        "macd": float(row.macd or 0),
                        "volatility_20d": float(row.volatility_20d or 0),
                        "max_drawdown_60d": float(row.max_drawdown_60d or 0),
                    }
                )
            session.close()
            emit_log("INFO", "screening", f"股票池加载: {len(universe)} 只")
        except Exception as e:
            emit_log("ERROR", "screening", f"股票池加载失败: {e}")
            if session:
                session.close()
        return universe

    def _apply_portfolio_context(self, recs: list[dict], holdings: dict) -> list[dict]:
        """Apply portfolio context. holdings format: {code: {quantity, profit_loss_pct}}"""
        if not holdings:
            return recs
        for rec in recs:
            code = rec.get("stock_code", "")
            if code in holdings:
                h = holdings[code]
                rec["in_portfolio"] = True
                rec["holding_qty"] = h.get("quantity", 0)
                rec["holding_pnl_pct"] = round(h.get("profit_loss_pct", 0), 2)
                score = rec.get("score", 50)
                current_signal = rec.get("signal", "观望")
                pnl = h.get("profit_loss_pct", 0)
                if pnl < -10:
                    if score >= 70:
                        rec["signal_note"] = f"持仓亏损{pnl:.1f}%, 但AI评分{score}较高, 暂持观察"
                    else:
                        rec["signal"] = "卖出"
                        rec["signal_note"] = f"止损: 持仓亏损{pnl:.1f}%"
                elif current_signal in ("买入", "bullish") and score >= 60:
                    rec["signal_note"] = "评分优良, 可加仓"
                elif current_signal in ("买入", "持有") and score < 40:
                    rec["signal"] = "卖出"
                    rec["signal_note"] = f"已持仓但评分降至{score}分, 建议减仓"
                elif current_signal == "买入" and score < 60:
                    rec["signal"] = "持有"
                    rec["signal_note"] = f"已持仓, 评分{score}分暂不加仓"
            else:
                rec["in_portfolio"] = False
        return recs

    def _save_style_signals(self, recs: list[dict]):
        """持久化风格信号"""
        try:
            from shared.models import StyleSignal, get_session

            session = get_session()
            for rec in recs[:20]:
                signal = StyleSignal(
                    stock_code=rec.get("stock_code", ""),
                    style=self.style,
                    score=rec.get("score", 0),
                    signal=rec.get("signal", ""),
                )
                session.add(signal)
            session.commit()
            session.close()
        except Exception as e:
            emit_log("DEBUG", "screening", f"信号持久化跳过: {e}")

    @staticmethod
    def _empty_pipeline_stats() -> dict:
        return {
            "stage3_total": 0,
            "stage3_pass": 0,
            "stage3_errors": 0,
            "avg_score": 0,
            "signal_distribution": {},
            "stage4_count": 0,
            "pipeline_time_s": 0,
        }
