"""统一日志系统 — 参考 TradingAgents-CN/utils/logging_init.py

提供一致的日志接口,支持:
- 分模块日志 (agents/graph/memory/llm)
- 详细调试模式
- 中文友好的日志格式
"""

import logging
import sys

_LOGGERS: dict[str, logging.Logger] = {}
_INITIALIZED = False


def _ensure_initialized():
    global _INITIALIZED  # noqa: PLW0603
    if _INITIALIZED:
        return
    _INITIALIZED = True

    # 根 logger 配置
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.setLevel(logging.INFO)


def get_logger(name: str = "default", level: int | None = None) -> logging.Logger:
    """获取命名 logger

    Args:
        name: logger 名称 (default/agents/graph/memory/llm)
        level: 可选的日志级别覆盖
    """
    _ensure_initialized()

    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(f"ashare.{name}")
    if level is not None:
        logger.setLevel(level)
    _LOGGERS[name] = logger
    return logger


def set_debug_mode(enabled: bool = True):
    """开启/关闭调试模式"""
    level = logging.DEBUG if enabled else logging.INFO
    logging.getLogger().setLevel(level)
    for logger in _LOGGERS.values():
        logger.setLevel(level)


# 预创建常用 logger
def get_agents_logger():
    return get_logger("agents")


def get_graph_logger():
    return get_logger("graph")


def get_memory_logger():
    return get_logger("memory")


def get_llm_logger():
    return get_logger("llm")
