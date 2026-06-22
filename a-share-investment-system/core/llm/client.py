"""LLM客户端 — 包装 skills.py"""

from typing import Any

from services.skill_engine import get_skill_engine

_engine = None


def _get_engine():
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = get_skill_engine()
    return _engine


def inject_skill(skill_name: str, context: str = "") -> str:
    """注入技能知识"""
    return str(_get_engine().inject_knowledge(skill_name, context))


def query_skills(context: str) -> list[Any]:
    """查询匹配的技能"""
    return list(_get_engine().query_by_context(context))
