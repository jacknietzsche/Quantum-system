"""单股深度分析API"""

import contextlib

from fastapi import APIRouter

from api.schemas.routes import AnalysisOut, AnalystScoreOut, ValuationOut
from shared.db_session import db_session
from shared.models import StockInfo

router = APIRouter()


@router.get("/{stock_code}", response_model=AnalysisOut)
def analyze_stock(stock_code: str):
    try:
        from services.data_initializer import DataInitializer
        from services.factor_farm import FactorFarm
        from services.quant_analyzers import QuantAnalyzers

        qa = QuantAnalyzers()
        ff = FactorFarm()

        def _sf(v, d=0.0):
            try:
                return float(v) if v is not None else d
            except (ValueError, TypeError, AttributeError):
                return d

        def _ss(v, d=""):
            try:
                return str(v) if v is not None else d
            except (Exception, AttributeError):
                return d

        # Extract all data inside session to avoid detached instance errors
        info_data = None
        with db_session() as session:
            info = session.query(StockInfo).filter_by(stock_code=stock_code).first()
            if info and _sf(info.latest_price) > 0:
                info_data = {
                    "stock_code": _ss(info.stock_code),
                    "stock_name": _ss(info.stock_name),
                    "industry": _ss(info.industry),
                    "latest_price": _sf(info.latest_price),
                    "roe": _sf(info.roe),
                    "debt_to_equity": _sf(info.debt_to_equity),
                    "gross_margin": _sf(info.gross_margin),
                    "eps": _sf(info.eps),
                    "bvps": _sf(info.bvps),
                    "pe_ratio": _sf(info.pe_ratio),
                    "earnings_growth_3y": _sf(info.earnings_growth_3y),
                    "cash_to_assets": _sf(getattr(info, "cash_to_assets", 0)),
                    "insider_holding_pct": _sf(getattr(info, "insider_holding_pct", 0)),
                    "shares_outstanding": _sf(getattr(info, "shares_outstanding", 0)),
                    "total_market_cap": _sf(info.total_market_cap),
                }

        # Auto-populate if data missing
        if not info_data:
            from shared.logging import emit_log

            emit_log("INFO", "analysis", f"Stock {stock_code} data incomplete, auto-populating...")
            di = DataInitializer()
            result = di.populate_stock_list([stock_code])
            if result.data.get("success", 0) > 0:
                with db_session() as session:
                    info = session.query(StockInfo).filter_by(stock_code=stock_code).first()
                    if info and _sf(info.latest_price) > 0:
                        info_data = {
                            "stock_code": _ss(info.stock_code),
                            "stock_name": _ss(info.stock_name),
                            "industry": _ss(info.industry),
                            "latest_price": _sf(info.latest_price),
                            "roe": _sf(info.roe),
                            "debt_to_equity": _sf(info.debt_to_equity),
                            "gross_margin": _sf(info.gross_margin),
                            "eps": _sf(info.eps),
                            "bvps": _sf(info.bvps),
                            "pe_ratio": _sf(info.pe_ratio),
                            "earnings_growth_3y": _sf(info.earnings_growth_3y),
                            "cash_to_assets": _sf(getattr(info, "cash_to_assets", 0)),
                            "insider_holding_pct": _sf(getattr(info, "insider_holding_pct", 0)),
                            "shares_outstanding": _sf(getattr(info, "shares_outstanding", 0)),
                            "total_market_cap": _sf(info.total_market_cap),
                        }

        if not info_data:
            return AnalysisOut(error=f"Cannot get data for {stock_code}")

        f = info_data.copy()
        buffett = qa.buffett_analyze(stock_code, f)
        graham = qa.graham_analyze(stock_code, f)
        lynch = qa.lynch_analyze(stock_code, f)
        factors = ff.get_top_factors(5).data

        return AnalysisOut(
            stock_code=stock_code,
            stock_name=info_data.get("stock_name", ""),
            valuation=ValuationOut(
                buffett=AnalystScoreOut(**buffett),
                graham=AnalystScoreOut(**graham),
                lynch=AnalystScoreOut(**lynch),
            ),
            factors=factors,
            signal=buffett.get("signal", "neutral"),
        )
    except Exception as e:
        return AnalysisOut(error=str(e))


@router.get("/v2/{stock_code}")
def analyze_stock_v2(stock_code: str, analysts: str = "market,sentiment,news,fundamentals"):
    """V2 multi-agent deep analysis (TradingAgents architecture)"""
    try:
        from datetime import datetime

        from graph_v2 import AShareTradingGraph
        from graph_v2.default_config import get_default_config

        config = get_default_config()
        analyst_list = [a.strip() for a in analysts.split(",") if a.strip()]

        graph = AShareTradingGraph(
            selected_analysts=analyst_list,
            config=config,
        )

        trade_date = datetime.now().strftime("%Y-%m-%d")
        decision, signal = graph.propagate(
            stock_code=stock_code,
            trade_date=trade_date,
            validate=True,
        )

        # Collect analyst reports from state
        reports = {}
        if graph.curr_state:
            for key in [
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
                "northbound_report",
                "sector_report",
            ]:
                val = graph.curr_state.get(key, "")
                if val:
                    reports[key] = val[:2000]

            # Get debate state
            debate = graph.curr_state.get("investment_debate_state", {})
            risk_debate = graph.curr_state.get("risk_debate_state", {})

            return {
                "ok": True,
                "stock_code": stock_code,
                "trade_date": trade_date,
                "decision": decision[:3000] if decision else "",
                "signal": signal,
                "reports": reports,
                "debate": {
                    "bull_history": debate.get("bull_history", "")[-1000:],
                    "bear_history": debate.get("bear_history", "")[-1000:],
                    "judge_decision": debate.get("judge_decision", ""),
                },
                "risk_debate": {
                    "aggressive": risk_debate.get("aggressive_history", "")[-500:],
                    "conservative": risk_debate.get("conservative_history", "")[-500:],
                    "neutral": risk_debate.get("neutral_history", "")[-500:],
                },
                "final_decision": graph.curr_state.get("final_trade_decision", "")[:1000],
                "master_factors": {
                    "master_weight_factor": graph.curr_state.get("master_weight_factor", 1.0),
                    "master_position_factor": graph.curr_state.get("master_position_factor", 1.0),
                },
            }

        return {
            "ok": True,
            "stock_code": stock_code,
            "trade_date": trade_date,
            "decision": decision[:3000] if decision else "",
            "signal": signal,
            "reports": {},
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 复盘API ──


@router.get("/daily-review")
def daily_review(force_date: str = ""):
    """执行日频复盘 — 对比昨日推荐 vs 今日实际表现"""
    try:
        from llm_clients.factory import get_client_for_role
        from services.screening.daily_review import DailyReview

        llm = None
        with contextlib.suppress(Exception):
            llm = get_client_for_role("secondary")

        review = DailyReview(llm_client=llm)
        return review.review_yesterday(force_trade_date=force_date if force_date else None)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/agent-stats")
def agent_stats(agent_name: str = ""):
    """查看Agent历史表现统计"""
    try:
        from services.screening.daily_memory import DailyMemory

        memory = DailyMemory()
        stats = memory.get_agent_stats(agent_name=agent_name if agent_name else None)

        # 补充准确率计算
        if stats:
            for s in stats:
                total = int(s.get("total_picks", 0) or 0)
                correct = int(s.get("correct", 0) or 0)
                s["accuracy"] = round(correct / max(total, 1), 4)

        return {"ok": True, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/memory-history")
def memory_history(days: int = 30):
    """查看历史记忆"""
    try:
        from services.screening.daily_memory import DailyMemory

        memory = DailyMemory()
        records = memory.get_recent(days=max(1, min(365, days)))
        return {"ok": True, "records": records}
    except Exception as e:
        return {"ok": False, "error": str(e)}
