"""QuantAgent API — AI投资决策引擎端点"""

from __future__ import annotations

import asyncio
import json
import threading

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from services.quant_agent import QuantAgent
from services.quant_agent.memory import MemorySystem
from shared.logging import emit_log

router = APIRouter(prefix="/api/quant-agent")

_agent_lock = threading.Lock()
_agent_running = False


@router.post("/daily-cycle")
def run_daily_cycle(force: bool = Query(False)):
    """手动触发AI每日决策循环 (同步模式)"""
    global _agent_running  # noqa: PLW0603
    with _agent_lock:
        if _agent_running:
            return {"status": "already_running"}
        _agent_running = True

    try:
        agent = QuantAgent()
        decision = agent.daily_cycle(force=force)
        return {
            "status": "ok",
            "date": decision.date,
            "picks_count": len(decision.picks),
            "picks": [p.__dict__ for p in decision.picks],
            "summary": decision.portfolio_summary,
            "warnings": decision.risk_warnings,
        }
    except Exception as e:
        emit_log("ERROR", "quant_agent", f"daily_cycle: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        _agent_running = False


@router.get("/daily-cycle/stream")
def run_daily_cycle_stream():
    """SSE流式推送AI思考过程"""

    async def event_generator():
        agent = QuantAgent()
        try:
            async for event in agent.daily_cycle_stream():
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                await asyncio.sleep(0.1)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/state")
def get_agent_state():
    """获取QuantAgent当前状态"""
    agent = QuantAgent()
    state = agent.get_state()
    return {
        "status": state.status,
        "current_phase": state.current_phase,
        "thoughts_count": len(state.thoughts),
        "final_picks_count": len(state.final_picks),
        "error": state.error,
    }


@router.get("/decision/{date}")
def get_decision(date: str):
    """获取某日的决策记录"""
    try:
        memory = MemorySystem()
        decision = memory.get_decision(date)
        reflection = memory.get_reflection(date)
        return {
            "status": "ok",
            "decision": decision,
            "reflection": reflection,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/decisions")
def list_decisions(limit: int = Query(10, ge=1, le=50)):
    """列出最近N天的决策"""
    try:
        memory = MemorySystem()
        decisions = memory.get_recent_decisions(limit)
        latest_reflection = memory.get_latest_reflection()
        return {
            "status": "ok",
            "decisions": decisions,
            "latest_reflection": latest_reflection,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
