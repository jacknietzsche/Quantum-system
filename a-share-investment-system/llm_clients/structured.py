"""结构化输出 + fallback 机制 — 参考 TradingAgents/agents/utils/structured.py

核心模式:
1. bind_structured(llm, schema) — 绑定 Pydantic schema
2. invoke_structured_or_freetext(...) — 结构化调用失败时降级为自由文本
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def bind_structured(llm: Any, schema: type[T], agent_name: str = "") -> Any | None:
    """返回 llm.with_structured_output(schema) 或 None (不支持时)

    当 provider 不支持结构化输出时记录警告,agent 将使用自由文本生成.
    """
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name or "agent",
            exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Any | None,
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str = "",
) -> str:
    """执行结构化调用并渲染为 markdown;失败时降级为自由文本.

    Args:
        structured_llm: 已绑定 schema 的 LLM (None 表示不支持)
        plain_llm: 原始 LLM 实例
        prompt: LLM 输入 (字符串或消息列表)
        render: 将结构化结果渲染为 markdown 的函数
        agent_name: agent 名称 (用于日志)

    Returns:
        markdown 格式的分析结果
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: structured-output failed (%s); retrying as free text",
                agent_name or "agent",
                exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)
