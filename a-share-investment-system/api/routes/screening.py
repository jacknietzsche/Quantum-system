"""选股API — 支持多风格选股(DB回退支持多worker)"""

import asyncio
import json
import threading
import traceback
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from services.portfolio import PortfolioService
from services.stock_screener import StockScreener
from shared.config import Config
from shared.logging import emit_log, get_logs_since
from shared.models import ScreenResult, get_session

router = APIRouter()


def _load_holdings(portfolio_type: str | None) -> dict:
    """根据 portfolio_type 从 DB 加载持仓映射 {stock_code: {quantity, profit_loss_pct, ...}}
    返回空 dict = 无持仓上下文。
    """
    if not portfolio_type:
        return {}
    try:
        svc = PortfolioService(get_session)
        return svc.get_holdings_map(portfolio_type)
    except Exception as e:
        emit_log("WARNING", "screening", f"加载持仓({portfolio_type})失败: {e}")
        return {}


_screening_lock = threading.Lock()
_screening_status: dict[str, Any] = {
    "running": False,
    "progress": 0,
    "results": None,
    "style": "hybrid",
}
_screening_abort = threading.Event()

LIVE_STATUS_RUN_ID = "_live_status"


def _write_live_status(**updates):
    """将当前选股进度写入 ScreenResult 表(跨 worker 可见)"""
    try:
        session = get_session()
        row = session.query(ScreenResult).filter_by(run_id=LIVE_STATUS_RUN_ID).first()
        if row:
            for k, v in updates.items():
                setattr(row, k, v)
            row.created_at = datetime.now()
        else:
            session.add(ScreenResult(run_id=LIVE_STATUS_RUN_ID, **updates))
        session.commit()
        session.close()
    except Exception as e:
        emit_log("WARNING", "screening", f"写入实时状态失败: {e}")


def _read_live_status() -> dict | None:
    """从 DB 读取跨 worker 的选股进度"""
    try:
        session = get_session()
        row = session.query(ScreenResult).filter_by(run_id=LIVE_STATUS_RUN_ID).first()
        session.close()
        if row and row.recommendations_json:
            return json.loads(row.recommendations_json)  # type: ignore[no-any-return]
    except Exception as e:
        emit_log("WARNING", "screening", f"读取实时状态失败: {e}")
    return None


STYLES = ["limit_up", "momentum", "value", "hybrid"]


def _cleanup_screen_results(max_keep: int = 500):
    """保留最近 max_keep 条 ScreenResult,删除更早的"""
    try:
        session = get_session()
        total = session.query(ScreenResult).count()
        if total > max_keep:
            row = (
                session.query(ScreenResult.id)
                .order_by(ScreenResult.created_at.desc())
                .offset(max_keep)
                .limit(1)
                .first()
            )
            if row:
                session.query(ScreenResult).filter(ScreenResult.id <= row[0]).delete()
                session.commit()
        session.close()
    except Exception as e:
        emit_log("WARNING", "screening", f"清理历史结果失败: {e}")


def _run_screening(style: str = "hybrid", portfolio_type: str | None = None):
    global _screening_status  # noqa: PLW0603
    _screening_status = {"running": False, "progress": 0, "results": None, "style": "hybrid"}
    _screening_abort.clear()
    _screening_status["progress"] = 10
    _screening_status["running"] = True
    _screening_status["style"] = style
    _write_live_status(
        style=style,
        total_universe=0,
        stage1_passed=0,
        stage3_recommended=0,
        status="running",
        recommendations_json=json.dumps({"progress": 10, "style": style}),
    )
    emit_log("INFO", "screening", f"[{style}] 选股启动...")
    try:
        ss = StockScreener(style=style)
        _screening_status["progress"] = 30
        _write_live_status(
            status="running", recommendations_json=json.dumps({"progress": 30, "style": style})
        )
        emit_log("INFO", "screening", f"[{style}] 运行 Pipeline...")
        if _screening_abort.is_set():
            raise InterruptedError("用户中止")
        holdings = _load_holdings(portfolio_type)
        result = ss.run(portfolio_holdings=holdings)
        _screening_status["results"] = result.data
        _screening_status["progress"] = 100
        n = len(result.data.get("recommendations", []))
        _write_live_status(
            style=style,
            status="completed",
            stage3_recommended=n,
            recommendations_json=json.dumps(result.data, ensure_ascii=False),
        )
        emit_log("INFO", "screening", f"[{style}] 完成 — {n} 只推荐")
    except InterruptedError:
        emit_log("WARNING", "screening", f"[{style}] 选程被用户中止")
    except Exception as e:
        emit_log("ERROR", "screening", f"[{style}] 选股失败: {e}")
        _screening_status["results"] = {"error": str(e), "style": style}
    _cleanup_screen_results(max_keep=500)
    with _screening_lock:
        _screening_status["running"] = False


def _run_screening_by_category(
    style: str = "hybrid", portfolio_type: str | None = None, top_n_per_category: int = 5
):
    """Run screening separately for each stock category."""
    global _screening_status  # noqa: PLW0603
    _screening_status = {"running": False, "progress": 0, "results": None, "style": style}
    _screening_abort.clear()
    _screening_status["progress"] = 10
    _screening_status["running"] = True
    _screening_status["style"] = style
    _write_live_status(
        style=style,
        total_universe=0,
        stage1_passed=0,
        stage3_recommended=0,
        status="running",
        recommendations_json=json.dumps({"progress": 10, "style": style}),
    )
    emit_log("INFO", "screening", f"[{style}] Category screening started...")
    try:
        ss = StockScreener(style=style)
        _screening_status["progress"] = 30
        if _screening_abort.is_set():
            raise InterruptedError("User aborted")
        holdings = _load_holdings(portfolio_type)
        result = ss.run_by_category(
            portfolio_holdings=holdings, top_n_per_category=top_n_per_category
        )
        _screening_status["results"] = result.data
        _screening_status["progress"] = 100
        n = len(result.data.get("recommendations", []))
        cats = result.data.get("categories", {})
        cat_summary = ", ".join(
            f"{v.get('category_name', k)}:{len(v.get('recommendations', []))}"
            for k, v in cats.items()
        )
        _write_live_status(
            style=style,
            status="completed",
            stage3_recommended=n,
            recommendations_json=json.dumps(result.data, ensure_ascii=False),
        )
        emit_log("INFO", "screening", f"[{style}] Done - {n} total ({cat_summary})")
    except InterruptedError:
        emit_log("WARNING", "screening", f"[{style}] Aborted by user")
    except Exception as e:
        emit_log("ERROR", "screening", f"[{style}] Failed: {e}")
        _screening_status["results"] = {"error": str(e), "style": style}
    _cleanup_screen_results(max_keep=500)
    with _screening_lock:
        _screening_status["running"] = False


@router.get("/run")
def run_screening(
    style: str = Query("hybrid", enum=["limit_up", "momentum", "value", "hybrid"]),
    portfolio_type: str = Query(None, enum=["limit_up", "momentum", "value"]),
):
    with _screening_lock:
        if _screening_status["running"]:
            return {"status": "already_running", "running_style": _screening_status.get("style")}
        _screening_status["running"] = True
        _screening_status["style"] = style
        _screening_status["progress"] = 0
    threading.Thread(target=_run_screening, args=(style, portfolio_type), daemon=True).start()
    return {"status": "started", "style": style, "portfolio_type": portfolio_type}


@router.get("/run/by-category")
def run_screening_by_category(
    style: str = Query("hybrid", enum=["limit_up", "momentum", "value", "hybrid"]),
    portfolio_type: str = Query(None, enum=["limit_up", "momentum", "value"]),
    top_n: int = Query(5, ge=1, le=20),
):
    """Run screening by category (STAR, ChiNext, Main, ETF, LOF) - returns 5 per category."""
    with _screening_lock:
        if _screening_status["running"]:
            return {"status": "already_running", "running_style": _screening_status.get("style")}
        _screening_status["running"] = True
        _screening_status["style"] = style
        _screening_status["progress"] = 0
    threading.Thread(
        target=_run_screening_by_category, args=(style, portfolio_type, top_n), daemon=True
    ).start()
    return {
        "status": "started",
        "style": style,
        "portfolio_type": portfolio_type,
        "mode": "by_category",
        "top_n": top_n,
    }


@router.get("/styles")
def list_styles():
    c = Config()
    styles = c.get("screening.styles", {})
    return {"styles": styles, "default": "hybrid"}


@router.get("/history")
def screening_history(limit: int = Query(20, ge=1, le=100)):
    try:
        session = get_session()
        rows = (
            session.query(ScreenResult).order_by(ScreenResult.created_at.desc()).limit(limit).all()
        )
        session.close()
        return {
            "count": len(rows),
            "history": [
                {
                    "run_id": r.run_id,
                    "style": r.style,
                    "total": r.total_universe,
                    "stage1": r.stage1_passed,
                    "stage2": r.stage2_passed,
                    "recommended": r.stage3_recommended,
                    "elapsed_s": r.elapsed_seconds,
                    "created_at": str(r.created_at)[:19],
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/status")
def screening_status():
    with _screening_lock:
        status = dict(_screening_status)
    # 本进程无 active 状态 → 尝试从 DB 读取跨 worker 状态
    if not status.get("running") and not status.get("results"):
        db_status = _read_live_status()
        if db_status:
            return db_status
    return status


@router.get("/results")
def screening_results():
    with _screening_lock:
        results = _screening_status.get("results", {})
        return dict(results) if results else {}


@router.post("/abort")
def abort_screening():
    """中止正在运行的选程 — 使用 threading.Event 实现协作取消"""
    _screening_abort.set()
    with _screening_lock:
        _screening_status["running"] = False
        _screening_status["progress"] = 0
    emit_log("INFO", "screening", "选程被用户中止")
    return {"status": "aborted"}


@router.get("/run/stream")
async def run_screening_stream(
    style: str = Query("hybrid", enum=["limit_up", "momentum", "value", "hybrid"]),
    portfolio_type: str = Query(None, enum=["limit_up", "momentum", "value"]),
):
    """SSE流式选股进度 — 支持多风格 + 持仓上下文"""

    async def generate():
        holdings = _load_holdings(portfolio_type)
        ss = StockScreener(style=style)
        _t0 = __import__("time").time()
        _log_idx = 0  # 增量日志游标

        def _log(level: str, msg: str) -> dict:
            return {"ts": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg}

        def _fetch_logs() -> list[dict]:
            nonlocal _log_idx
            entries, _log_idx = get_logs_since(_log_idx)
            # 只返回 screening 模块的日志
            return [e for e in entries if e.get("module") == "screening"]

        emit_log("INFO", "screening", f"SSE [{style}] 流式启动")
        _pf = portfolio_type or "无"
        yield f"data: {json.dumps({'type': 'stage', 'stage': 0, 'msg': f'[{style}] 数据加载', 'style': style, 'details': {'step': 'start', 'style': style, 'stage': '初始化', 'portfolio_type': _pf}, 'logs': [_log('INFO', f'[{style}] 启动选股流水线'), _log('INFO', f'风格: {style}'), _log('INFO', f'持仓: {_pf}')]}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)

        try:
            universe = await asyncio.to_thread(ss._load_universe)
            t1 = __import__("time").time()
            yield f"data: {json.dumps({'type': 'stage', 'stage': 1, 'msg': f'[{style}] {len(universe)}只加载完成', 'progress': 30, 'style': style, 'details': {'universe': len(universe), 'elapsed_s': round(t1 - _t0, 1), 'stage': '数据加载', 'status': 'OK'}, 'logs': [_log('INFO', f'股票池: {len(universe)} 只'), _log('INFO', f'查询耗时: {round(t1 - _t0, 1)}s')]}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.1)

            # 后台运行 pipeline,同时心跳轮询日志 — 传入持仓上下文
            _current_stage = 1  # stage:1 已发送
            _current_progress = 30

            def _on_progress(pct: int, msg: str = ""):
                """Pipeline progress callback → 注入日志流供 heartbeat 捕获"""
                emit_log("INFO", "screening", f"[PROGRESS]|{pct}|{msg}")

            pipeline_task = asyncio.create_task(
                asyncio.to_thread(
                    ss.run,
                    stock_universe=universe,
                    portfolio_holdings=holdings,
                    progress_callback=_on_progress,
                )
            )

            def _detect_stage(msg: str) -> int:
                # 返回 0-based 前端 stages 索引:
                if "Stage1" in msg or "HardFilter" in msg or "初筛" in msg:
                    return 1  # → 市场扫描
                if "Stage2" in msg or "量化大师" in msg or "预评分" in msg:
                    return 2  # → AI分析
                if "Stage3" in msg or "StockAgent" in msg or "LLM" in msg or "锚定AI" in msg:
                    return 2  # → AI分析 (Stage2+3 都是 AI 分析阶段)
                if "Stage4" in msg or "辩论" in msg:
                    return 3  # → 辩论裁决
                return -1

            while not pipeline_task.done():
                await asyncio.sleep(1)
                fresh_logs = _fetch_logs()
                # 从增量日志检测阶段推进和进度
                for log in fresh_logs:
                    msg = log.get("msg", "")
                    s = _detect_stage(msg)
                    _current_stage = max(_current_stage, s)
                    # 从 progress_callback 注入的日志提取精确进度
                    if msg.startswith("[PROGRESS]|"):
                        try:
                            pct = int(msg.split("|")[1])
                            _current_progress = max(_current_progress, pct)
                        except (IndexError, ValueError):
                            # 进度字段格式异常时忽略
                            pass
                # 无精确进度时用阶段映射兜底
                _stage_progress = {1: 30, 2: 45, 3: 60, 4: 85}
                progress = (
                    _current_progress
                    if _current_progress > 30
                    else _stage_progress.get(_current_stage, 50)
                )

                payload = {
                    "type": "heartbeat",
                    "stage": _current_stage,
                    "progress": progress,
                    "style": style,
                }
                if fresh_logs:
                    payload["logs"] = fresh_logs
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            result = pipeline_task.result()
            t2 = __import__("time").time()
            data = result.data if hasattr(result, "data") else {}
            data["style"] = style
            n = len(data.get("recommendations", []))
            passed = data.get("filter_passed", data.get("stage2_passed", 0))
            stats = data.get("pipeline_stats", {})
            stage4_analyses = data.get("stage4_analyses", [])

            stage2_details = {
                "analyzed": len(stage4_analyses) if stage4_analyses else passed,
                "filter_passed": passed,
                "elapsed_s": round(t2 - _t0, 1),
                "stage": "AI分析",
                "llm_total": stats.get("stage3_total", 0),
                "llm_errors": stats.get("stage3_errors", 0),
                "llm_pass": stats.get("stage3_pass", 0),
            }
            stage2_logs = [
                _log("INFO", f"HardFilter 通过: {passed} 只"),
                _log("INFO", f"LLM 分析: {stats.get('stage3_total', 0)} 只"),
            ]
            if stats.get("stage3_errors", 0) > 0:
                stage2_logs.append(
                    _log("WARNING", f"LLM 失败: {stats['stage3_errors']} 只 (429/超时)")
                )
            stage2_logs.append(_log("INFO", f"LLM 达标(>=60): {stats.get('stage3_pass', 0)} 只"))
            if stage4_analyses:
                stage2_logs.append(_log("INFO", f"Stage4 辩论: {len(stage4_analyses)} 只"))
            if stage4_analyses:
                yield f"data: {json.dumps({'type': 'stage', 'stage': 2, 'msg': f'[{style}] AI分析完成', 'progress': 70, 'stage4_analyses': stage4_analyses, 'style': style, 'details': stage2_details, 'logs': stage2_logs}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.1)

            signal_dist = stats.get("signal_distribution", {})
            stage3_logs = [
                _log("INFO", f"推荐: {n} 只"),
                _log("INFO", f"平均分: {stats.get('avg_score', 0)}"),
            ]
            if signal_dist:
                stage3_logs.append(
                    _log("INFO", f"信号分布: {json.dumps(signal_dist, ensure_ascii=False)}")
                )
            if stats.get("stage4_count", 0) > 0:
                stage3_logs.append(_log("INFO", f"Stage4 辩论裁决: {stats['stage4_count']} 只"))
            stage3_logs.append(_log("INFO", f"总耗时: {round(t2 - _t0, 1)}s"))

            yield f"data: {json.dumps({'type': 'stage', 'stage': 3, 'msg': f'[{style}] 完成! {n}只推荐', 'progress': 100, 'results': data, 'style': style, 'details': {'recommended': n, 'total_elapsed_s': round(t2 - _t0, 1), 'stage': '完成', 'avg_score': stats.get('avg_score', 0), 'signal_dist': json.dumps(signal_dist, ensure_ascii=False) if signal_dist else ''}, 'logs': stage3_logs}, ensure_ascii=False)}\n\n"
        except Exception as e:
            emit_log("ERROR", "screening", f"SSE [{style}] 选股失败: {e}")
            yield f"data: {json.dumps({'type': 'stage', 'stage': -1, 'msg': f'[{style}] 选股失败: {e}', 'progress': 0, 'error': str(e), 'style': style, 'logs': [_log('ERROR', f'选股失败: {e}'), _log('ERROR', traceback.format_exc()[:200])]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/generate-plan")
def generate_trading_plan(data: dict | None = None):
    """根据最新选股结果生成交易计划 - 日频策略核心端点

    body (可选):
        style: str = "hybrid"  选股风格
        portfolio_type: str = "value"  组合类型
        run_id: str = None  指定选股运行ID(默认用最新)
    """
    try:
        from services.data_bus import DatabaseBackedDataBus
        from services.market_perception import MarketPerception
        from services.portfolio import PortfolioService
        from services.risk_engine import RiskEngine
        from services.trading_plan import (
            TradingPlanGenerator,
            extract_master_factors,
        )

        data = data or {}
        style = data.get("style", "hybrid")
        portfolio_type = data.get("portfolio_type", "value")
        run_id = data.get("run_id")

        # 1. 获取最新选股结果
        session = get_session()
        if run_id:
            row = session.query(ScreenResult).filter_by(run_id=run_id).first()
        else:
            row = (
                session.query(ScreenResult)
                .filter(ScreenResult.status == "completed", ScreenResult.run_id != "_live_status")
                .order_by(ScreenResult.created_at.desc())
                .first()
            )
        session.close()

        if not row or not row.recommendations_json:
            return {
                "error": "No screening results found. Run screening first.",
                "status": "no_data",
            }

        recs = json.loads(row.recommendations_json)
        screening_data = recs if isinstance(recs, dict) else {"recommendations": recs}
        recommendations = screening_data.get("recommendations", [])

        if not recommendations:
            return {"error": "Empty recommendations", "status": "empty"}

        # 2. 获取当前持仓
        ps = PortfolioService(get_session)
        holdings_result = ps.get_holdings(portfolio_type)
        positions = holdings_result.get("positions", []) if holdings_result else []
        cash = holdings_result.get("cash", 0) if holdings_result else 0
        total_asset = holdings_result.get("total_asset", 0) if holdings_result else 0

        # 3. 获取风险评估
        re = RiskEngine()
        mp = MarketPerception()
        data_bus = DatabaseBackedDataBus()
        breadth = data_bus.get_market_breadth()
        indices = data_bus.get_market_indices()
        regime = mp.perceive({"breadth": breadth or {}, "indices": indices or {}}).data
        risk_report = re.full_audit(positions, regime).data

        # 4. 生成交易计划
        tpg = TradingPlanGenerator()
        _factors = extract_master_factors(screening_data)
        plan_result = tpg.generate(
            recommendations=recommendations,
            current_positions=positions,
            risk_report=risk_report,
            cash=cash,
            total_capital=total_asset
            or (cash + sum(p.get("current_value", p.get("cost_value", 0)) for p in positions)),
            master_position_factor=_factors["master_position_factor"],
            master_weight_factor=_factors["master_weight_factor"],
        )

        if not plan_result.data:
            return {"error": plan_result.errors, "status": "failed"}

        plan = plan_result.data
        plan["screening_run_id"] = row.run_id
        plan["screening_style"] = style
        plan["portfolio_type"] = portfolio_type
        plan["market_regime"] = regime.get("regime", "NEUTRAL")

        return plan
    except Exception as e:
        emit_log("ERROR", "screening", f"generate_trading_plan: {e}")
        return {"error": str(e), "status": "failed"}


@router.get("/daily-summary")
def daily_screening_summary():
    """日频分析摘要 - 最新选股结果 + 风险状态 + 交易计划概要"""
    try:
        from services.data_bus import DatabaseBackedDataBus
        from services.market_perception import MarketPerception
        from services.risk_engine import RiskEngine
        from services.trade_executor import TradeExecutor

        # 最新选股结果
        session = get_session()
        latest = (
            session.query(ScreenResult)
            .filter(ScreenResult.status == "completed", ScreenResult.run_id != "_live_status")
            .order_by(ScreenResult.created_at.desc())
            .first()
        )
        session.close()

        latest_recs = []
        latest_meta = {}
        if latest and latest.recommendations_json:
            data = json.loads(latest.recommendations_json)
            if isinstance(data, dict):
                latest_recs = data.get("recommendations", [])
                latest_meta = {
                    "run_id": latest.run_id,
                    "style": latest.style,
                    "created_at": str(latest.created_at),
                    "total_universe": latest.total_universe,
                    "stage1_passed": latest.stage1_passed,
                    "elapsed_seconds": latest.elapsed_seconds,
                }

        # 市场状态
        mp = MarketPerception()
        data_bus = DatabaseBackedDataBus()
        breadth = data_bus.get_market_breadth()
        indices = data_bus.get_market_indices()
        regime = mp.perceive({"breadth": breadth or {}, "indices": indices or {}}).data

        # 风险状态
        re = RiskEngine()
        te = TradeExecutor()
        positions_result = te.get_positions()
        positions = positions_result.data.get("positions", []) if positions_result.data else []
        risk_report = re.full_audit(positions, regime).data

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "market_regime": regime.get("regime", "NEUTRAL"),
            "risk_level": risk_report.get("risk_level", "MEDIUM") if risk_report else "MEDIUM",
            "latest_screening": latest_meta,
            "recommendations_count": len(latest_recs),
            "top_recommendations": latest_recs[:5],
            "position_count": len(positions),
            "has_positions": len(positions) > 0,
            "kill_switch": te.check_kill_switch().data,
        }
    except Exception as e:
        emit_log("ERROR", "screening", f"daily_summary: {e}")
        return {"error": str(e)}


@router.get("/market-state")
def market_state(force_refresh: bool = Query(False)):
    """市场诊断 — 返回当前市场状态+动态权重+详细指标

    数据来源: 现有DB + MarketSnapshot, 无外部调用 (LLM模式可选)。
    结果当日缓存。
    """
    try:
        # 尝试激活LLM模式
        mp = _create_perception_with_llm()
        diagnosis = mp.diagnose(force_refresh=force_refresh)

        return {
            "status": "ok",
            "state": diagnosis.state,
            "confidence": diagnosis.confidence,
            "weights": diagnosis.weights,
            "summary": diagnosis.summary,
            "timestamp": diagnosis.timestamp,
            "details": diagnosis.details,
        }
    except Exception as e:
        emit_log("ERROR", "screening", f"market_state: {e}")
        return {
            "status": "error",
            "error": str(e),
            "state": "SHOCK",
            "weights": {"trend": 0.25, "capital": 0.25, "fundamental": 0.25, "defensive": 0.25},
        }


def _create_perception_with_llm():
    """创建市场感知实例, 尝试配置LLM client"""
    from services.screening.market_perception import MarketPerception

    try:
        from llm_clients.factory import get_client_for_role

        client = get_client_for_role("secondary")
        if client is not None:
            emit_log("INFO", "screening", "市场感知: LLM模式已激活")
            return MarketPerception(llm_client=client)
    except Exception as e:
        emit_log("DEBUG", "screening", f"市场感知LLM不可用, 使用规则降级: {e}")
    return MarketPerception()  # 规则降级
