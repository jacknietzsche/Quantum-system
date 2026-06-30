"""分析相关路由。

启动真实LangGraph工作流分析股票，通过SSE推送实时进度。
设计依据: S06 §6.1, S14 §14.2。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("ashare-x.api.analysis")

router = APIRouter(prefix="/api", tags=["analysis"])


class AnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$",
                        description="6位A股代码，如 600519")
    fast_mode: bool = False
    enable_masters: bool = False


class AnalysisJob(BaseModel):
    job_id: str
    ticker: str
    status: str = "pending"


_jobs: dict[str, dict] = {}
_background_tasks: set[asyncio.Task] = set()

# 并发分析任务上限，防止事件循环/线程池资源耗尽导致进程崩溃
MAX_CONCURRENT_ANALYSES = 2


def _count_running_jobs() -> int:
    return sum(1 for j in _jobs.values() if j.get("status") == "running")


AGENT_LABELS = {
    "market_analyst": "市场分析师",
    "fundamentals_analyst": "基本面分析师",
    "news_analyst": "新闻分析师",
    "sentiment_analyst": "情绪分析师",
    "bull_researcher": "看涨研究员",
    "bear_researcher": "看跌研究员",
    "research_manager": "研究经理",
    "trader": "交易员",
    "aggressive_analyst": "激进分析师",
    "conservative_analyst": "保守分析师",
    "neutral_analyst": "中性分析师",
    "portfolio_manager": "组合经理",
    "master_selector": "大师选择器",
    "master_review": "大师评审",
}


@router.post("/analysis", response_model=AnalysisJob)
async def start_analysis(req: AnalysisRequest):
    """启动个股分析。"""
    # 并发上限保护，防止进程崩溃
    if _count_running_jobs() >= MAX_CONCURRENT_ANALYSES:
        raise HTTPException(
            429,
            f"已有 {_count_running_jobs()} 个分析任务在运行，最多并发 {MAX_CONCURRENT_ANALYSES} 个，请稍后再试",
        )
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "ticker": req.ticker,
        "status": "running",
        "progress": 0,
        "result": None,
        "agents_status": {},
        "log_queue": asyncio.Queue(),
    }
    task = asyncio.create_task(
        _run_analysis(job_id, req.ticker, req.fast_mode, req.enable_masters)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return AnalysisJob(job_id=job_id, ticker=req.ticker, status="running")


@router.get("/analysis/{job_id}")
async def get_analysis(job_id: str):
    """查询分析状态。"""
    if job_id not in _jobs:
        raise HTTPException(404, "Job not found")
    job = _jobs[job_id]
    # Exclude log_queue (asyncio.Queue is not JSON serializable)
    return {k: v for k, v in job.items() if k != "log_queue"}


@router.delete("/analysis/{job_id}")
async def cancel_analysis(job_id: str):
    """取消分析任务。"""
    if job_id not in _jobs:
        raise HTTPException(404, "Job not found")
    _jobs[job_id]["status"] = "cancelled"
    return {"ok": True}


@router.get("/stream/{job_id}")
async def stream_analysis(job_id: str):
    """SSE实时推送分析进度。"""
    if job_id not in _jobs:
        raise HTTPException(404, "Job not found")

    async def event_generator():
        last_progress = -1
        sent_agents: set[str] = set()

        while True:
            job = _jobs.get(job_id)
            if not job:
                break

            # 发送进度更新
            current_progress = min(max(job["progress"], 0), 100)
            if current_progress != last_progress:
                progress_data = {
                    "progress": current_progress,
                    "agent": job.get("current_agent", ""),
                    "status": job["status"],
                }
                yield f"event: progress\ndata: {json.dumps(progress_data)}\n\n"
                last_progress = current_progress

            # 发送Agent状态变更
            for agent, status in job.get("agents_status", {}).items():
                if agent not in sent_agents:
                    sent_agents.add(agent)
                    agent_data = {
                        "agent": agent,
                        "label": AGENT_LABELS.get(agent, agent),
                        "status": status,
                    }
                    yield f"event: agent_status\ndata: {json.dumps(agent_data)}\n\n"

            # 发送日志
            log_queue: asyncio.Queue = job.get("log_queue")
            if log_queue:
                while not log_queue.empty():
                    try:
                        log_msg = log_queue.get_nowait()
                        yield f"event: log\ndata: {json.dumps(log_msg)}\n\n"
                    except asyncio.QueueEmpty:
                        break

            # 任务完成
            if job["status"] in ("completed", "failed", "cancelled"):
                done_data = {"status": job["status"], "result": job.get("result")}
                yield f"event: done\ndata: {json.dumps(done_data)}\n\n"
                break

            await asyncio.sleep(0.2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _log(job: dict, level: str, message: str):
    """向job的日志队列推送消息。"""
    import contextlib

    log_queue: asyncio.Queue = job.get("log_queue")
    if log_queue:
        with contextlib.suppress(asyncio.QueueFull):
            log_queue.put_nowait({"level": level, "message": message, "time": _now()})


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")


async def _animate_progress(job: dict):
    """在LangGraph同步执行期间，定期推进进度条，避免前端卡死。"""
    try:
        while job.get("status") == "running":
            await asyncio.sleep(5)
            if job.get("status") != "running":
                break
            # Never exceed 85 during animation; clamp to [0, 85]
            current = job.get("progress", 0)
            if current < 85:
                job["progress"] = min(current + 5, 85)
    except asyncio.CancelledError:
        pass


async def _run_analysis(
    job_id: str, ticker: str, fast_mode: bool, enable_masters: bool
):
    """后台分析任务 — 调用真实LangGraph工作流。"""
    job = _jobs[job_id]

    try:
        _log(job, "info", f"开始分析 {ticker} (模式: {'快速' if fast_mode else '完整'})")

        # 1. 创建LLM客户端
        from core.config import Config
        from core.llm_client import LLMClient

        config = Config()
        llm_client = LLMClient(config)

        # 检查API Key是否配置
        api_key = config.get("llm.deepseek.api_key", "")
        if not api_key:
            # 尝试从环境变量获取
            import os

            api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            _log(job, "error", "未配置DEEPSEEK_API_KEY，无法执行分析")
            job["status"] = "failed"
            job["result"] = {"error": "未配置API Key"}
            return

        # 2. 构建工作流图（带checkpointer，支持断点恢复）
        _log(job, "info", "构建分析工作流...")
        from graph.trading_graph import build_trading_graph

        graph = build_trading_graph(llm_client)
        _log(job, "info", "工作流构建完成（已启用状态持久化）")

        # 3. 创建初始状态
        from core.state import make_initial_state

        state = make_initial_state(
            ticker=ticker,
            mode="fast" if fast_mode else "full",
        )
        # 添加配置
        state["config"] = {
            "debate": {
                "investment": {"max_rounds": 1 if fast_mode else 2},
                "risk": {"max_rounds": 1 if fast_mode else 2},
            },
            "features": {"enable_masters": enable_masters},
        }

        # 4. 在线程池中执行工作流（LangGraph是同步的）
        _log(job, "info", "开始执行Agent工作流...")

        # 更新进度
        job["current_agent"] = "market_analyst"
        job["agents_status"]["market_analyst"] = "in_progress"
        job["progress"] = 5
        _log(job, "info", "市场分析师开始分析...")

        # 启动进度动画任务，避免前端长时间停留在5%
        progress_task = asyncio.create_task(_animate_progress(job))

        # 执行工作流（在线程池中运行同步代码，thread_id用于checkpointer持久化）
        thread_config = {"configurable": {"thread_id": job_id}}
        loop = asyncio.get_event_loop()
        try:
            final_state = await loop.run_in_executor(
                None, lambda: graph.invoke(state, config=thread_config)
            )
        finally:
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

        # 5. 解析结果
        job["progress"] = min(90, 100)
        _log(job, "info", "分析完成，解析结果...")

        # 更新所有Agent状态为完成
        for agent in AGENT_LABELS:
            job["agents_status"][agent] = "completed"

        # 从final_state提取决策
        result = _parse_analysis_result(final_state, ticker, job_id)

        # 从LLM客户端获取预算快照
        budget_snapshot = llm_client.get_budget_snapshot()
        if budget_snapshot:
            result["budget"] = budget_snapshot

        job["result"] = result
        job["progress"] = 100
        job["status"] = "completed"
        _log(job, "success", f"分析完成: {result.get('action', 'N/A')}")

    except Exception as e:
        logger.error("分析失败 %s: %s", ticker, e, exc_info=True)
        _log(job, "error", f"分析失败: {e}")
        job["status"] = "failed"
        job["result"] = {"error": str(e)}


def _parse_analysis_result(final_state: dict, ticker: str, job_id: str = "") -> dict:
    """从LangGraph最终状态解析分析结果。"""
    result: dict = {"ticker": ticker}

    # 尝试从portfolio_manager_report解析最终决策
    pm_report = final_state.get("portfolio_manager_report", "")
    if pm_report:
        # 尝试从报告文本中提取JSON
        try:
            import re

            json_match = re.search(r"\{[^{}]*\}", pm_report.replace("\n", " "))
            if json_match:
                decision = json.loads(json_match.group())
                result["action"] = decision.get("rating", "Hold")
                result["confidence"] = decision.get("confidence", 70)
                result["entry_price"] = decision.get("entry_price")
                result["stop_loss"] = decision.get("stop_loss")
                result["take_profit"] = decision.get("take_profit")
                result["position_pct"] = decision.get("position_pct", 5.0)
                result["executive_summary"] = decision.get("executive_summary", "")
        except (json.JSONDecodeError, AttributeError):
            result["action"] = "Hold"
            result["confidence"] = 70
            result["thesis"] = pm_report[:500] if pm_report else ""

    # 收集分析师信号
    signals = final_state.get("analyst_signals", {})
    if signals:
        result["analyst_signals"] = signals

    # 收集大师Agent信号
    master_signals = final_state.get("master_signals", {})
    if master_signals:
        result["master_signals"] = master_signals

    # 收集各Agent报告摘要
    reports: dict[str, str] = {}
    for key, value in final_state.items():
        if isinstance(value, str) and value and (
            key.endswith(("_report", "_decision", "_proposal"))
        ):
            reports[key] = value[:2000]
        elif isinstance(value, dict) and value and (
            key.endswith(("_decision", "_proposal"))
        ):
            reports[key] = json.dumps(value, ensure_ascii=False, indent=2)[:2000]

    # 预算/Token消耗
    budget = final_state.get("budget_snapshot")
    if budget:
        result["budget"] = budget
    if reports:
        result["reports"] = reports

    # 确保关键字段有默认值
    result.setdefault("action", "Hold")
    result.setdefault("confidence", 70)
    result.setdefault("position_pct", 5.0)
    result.setdefault("thesis", "综合分析完成")

    # 保存报告到数据库
    try:
        from services.report import ReportGenerator

        report_gen = ReportGenerator()
        report_gen.save_report(
            report_id=job_id,
            plan=result,
            agents=list(AGENT_LABELS.keys()),
        )
    except Exception as e:
        logger.warning("保存报告失败: %s", e)

    # 记录决策日志
    try:
        from datetime import date as _date

        from memory.decision_log import DecisionLog

        log = DecisionLog()
        log.add_entry(
            ticker=ticker,
            date=result.get("date") or _date.today().isoformat(),
            action=result.get("action", "Hold"),
            confidence=result.get("confidence", 70),
            thesis=result.get("thesis", ""),
        )

        # 反思：检查该ticker的历史决策，如果有旧决策且当前价格已知，更新结果
        history = log.get_history(ticker, limit=3)
        if len(history) > 1:
            prev = history[1]  # 第二条是上一次决策
            if prev.get("entry_price") and result.get("entry_price"):
                prev_entry = prev["entry_price"]
                current_price = result.get("entry_price", 0)
                if prev_entry > 0:
                    profit = current_price - prev_entry
                    return_pct = (profit / prev_entry) * 100
                    log.update_outcome(
                        entry_id=prev["id"],
                        profit=round(profit, 2),
                        return_pct=round(return_pct, 2),
                    )
    except Exception as e:
        logger.warning("记录决策日志失败: %s", e)

    # 存入向量库供RAG检索
    try:
        from memory.vectorstore import get_vectorstore

        vs = get_vectorstore()
        if vs.available and reports:
            combined = "\n\n".join(
                f"[{k}]\n{v}" for k, v in reports.items()
            )
            vs.add_report(
                ticker=ticker,
                report_text=combined,
                report_type="analysis",
            )
            logger.info("分析报告已存入向量库")
    except Exception as e:
        logger.warning("存入向量库失败: %s", e)

    return result
