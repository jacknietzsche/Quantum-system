"""国际化消息 (见 exp12.1, S03 §3.x 语言配置)。

设计:
- 消息按 key 组织, 支持 zh / en 两语。
- lang 由 Config.get("log.lang", "zh") 决定, 可被 env ASHARE_X_LANG 覆盖。
- 异常的 i18n_key 经 translate() 渲染, 找不到 key 时回退到英文模板, 再回退到 key 本身。

线程安全: 模块级只读字典, 运行时不可变 (除非测试调 set_lang)。
"""

from __future__ import annotations

import string
import threading
from typing import Any

# ── 消息字典 ──────────────────────────────────────────────────────
# 与 core/exceptions.py 的 i18n_key 对应
_MESSAGES: dict[str, dict[str, str]] = {
    "error.generic": {
        "zh": "发生错误: {message}",
        "en": "An error occurred: {message}",
    },
    "error.config": {
        "zh": "配置错误: {message}",
        "en": "Configuration error: {message}",
    },
    "error.data": {
        "zh": "数据错误: {message}",
        "en": "Data error: {message}",
    },
    "error.data_source": {
        "zh": "数据源 {source} 不可用: {message}",
        "en": "Data source {source} unavailable: {message}",
    },
    "error.data_not_found": {
        "zh": "未找到数据: {message}",
        "en": "Data not found: {message}",
    },
    "error.data_validation": {
        "zh": "数据校验失败: {message}",
        "en": "Data validation failed: {message}",
    },
    "error.llm": {
        "zh": "LLM 调用失败: {message}",
        "en": "LLM call failed: {message}",
    },
    "error.llm_timeout": {
        "zh": "LLM 调用超时: {message}",
        "en": "LLM call timed out: {message}",
    },
    "error.llm_rate_limit": {
        "zh": "LLM 限流, 请稍后重试 (retry_after={retry_after}s): {message}",
        "en": "LLM rate limited, retry later (retry_after={retry_after}s): {message}",
    },
    "error.llm_response": {
        "zh": "LLM 响应解析失败: {message}",
        "en": "LLM response parsing failed: {message}",
    },
    "error.workflow": {
        "zh": "工作流错误: {message}",
        "en": "Workflow error: {message}",
    },
    "error.budget_exceeded": {
        "zh": ("月预算超限 (已用 ¥{used_rmb:.2f} / 预算 ¥{budget_rmb:.2f}): {message}"),
        "en": (
            "Monthly budget exceeded (used ¥{used_rmb:.2f} / budget ¥{budget_rmb:.2f}): {message}"
        ),
    },
}

# ── 当前语言 (模块级, 可热切) ────────────────────────────────────
_current_lang: str = "zh"
_lock = threading.RLock()

_SUPPORTED = ("zh", "en")


def set_lang(lang: str) -> None:
    """设置当前语言 (主要供 Config 加载时调用 / 测试)。"""
    global _current_lang  # noqa: PLW0603
    lang = lang.lower()
    if lang not in _SUPPORTED:
        raise ValueError(f"不支持的语言: {lang!r}, 仅支持 {_SUPPORTED}")
    with _lock:
        _current_lang = lang


def get_lang() -> str:
    with _lock:
        return _current_lang


def translate(key: str, **kwargs: Any) -> str:
    """渲染消息。

    回退顺序: zh/en 模板 -> 英文模板 -> key 本身。
    只替换 kwargs 中提供的占位符; 缺失的占位符保留原样 (用 Formatter.partial, 不抛错)。
    这样 DataSourceError(message=...) 即使没传 source 也能正确填入 message。
    """
    lang = get_lang()
    entry = _MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(lang) or entry.get("en") or key
    try:
        return _SafeFormatter().format(template, **kwargs)
    except (KeyError, IndexError, ValueError):
        return template


class _SafeFormatter(string.Formatter):
    """只替换已提供的字段名, 缺失的字段保留 {name} 原样。"""

    def get_value(self, key: Any, args: tuple, kwargs: dict) -> Any:  # type: ignore[override]
        if isinstance(key, str):
            if key in kwargs:
                return kwargs[key]
            # 缺失: 抛出供 vformat 捕获的特殊标记, 由 field_name 重建原占位符
            raise _MissingField(key)
        return super().get_value(key, args, kwargs)

    def vformat(self, format_string: str, args: tuple, kwargs: dict) -> str:  # type: ignore[override]
        # 基类 vformat 不捕获 get_value 抛出的异常, 这里包一层逐字段处理
        result: list[str] = []
        for literal_text, field_name, format_spec, conversion in self.parse(format_string):
            result.append(literal_text)
            if field_name is None:
                continue
            try:
                obj = self.get_field(field_name, args, kwargs)[0]
            except _MissingField:
                # 还原 {field_name} / {field_name:spec} 原样
                spec = f":{format_spec}" if format_spec else ""
                result.append("{" + field_name + spec + "}")
            else:
                obj = self._convert(obj, conversion)
                result.append(self.format_field(obj, format_spec))
        return "".join(result)

    @staticmethod
    def _convert(obj: Any, conversion: str | None) -> Any:
        if conversion == "r":
            return repr(obj)
        if conversion == "s":
            return str(obj)
        if conversion == "a":
            return ascii(obj)
        return obj


class _MissingField(KeyError):
    """内部标记: 占位符对应的字段未提供。"""


def translate_exception(exc: BaseException) -> str:
    """从异常的 i18n_key + details + args 渲染用户消息。"""
    i18n_key = getattr(exc, "i18n_key", "error.generic")
    details: dict = getattr(exc, "details", {}) or {}
    # message 取 str(exc) (异常的 args[0]) 兜底
    details.setdefault("message", str(exc.args[0]) if exc.args else "")
    return translate(i18n_key, **details)
