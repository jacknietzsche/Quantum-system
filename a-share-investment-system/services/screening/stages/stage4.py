"""Stage4: Agent 深度分析 — 从 stock_screener.py._run_stage4_agent_workflow() 拆分"""

from __future__ import annotations

from typing import Any

from shared.logging import emit_log


def stage4_agent_workflow(
    candidates: list[dict],
    config: Any,
    style: str = "hybrid",
) -> list[dict]:
    """Stage4: Agent 深度分析 (可选)

    Args:
        candidates: Stage3 通过的候选股
        config: Stage4Config 数据类
        style: 选股风格
    """
    if not config.enabled or not candidates:
        return []

    try:
        from services.agent_workflow import AgentWorkflowService

        agent_service = AgentWorkflowService(
            style=style,
            config={
                "model": config.model,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
            },
        )
        result = agent_service.batch_analyze(candidates, top_n=config.top_n)
        if result.status == "ok":
            return result.data.get("analyses", [])
    except Exception as e:
        emit_log("WARNING", "screening", f"[{style}] Stage4 agent failed: {e}")

    return []
