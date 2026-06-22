"""共享日志模块 — 内存环形缓冲区 + Logger工厂,供全系统使用"""

import logging
import threading
from datetime import datetime

_log_buffer: list[dict] = []
_MAX_BUFFER = 500
_log_lock = threading.Lock()


def get_logger(name: str) -> logging.Logger:
    """获取标准 Logger 实例, 自动配置 emit_log Handler"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger


def emit_log(level: str, module: str, message: str):
    """写入环形缓冲区(线程安全)"""
    entry = {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "module": module,
        "msg": message[:500],
    }
    with _log_lock:
        _log_buffer.append(entry)
        if len(_log_buffer) > _MAX_BUFFER:
            _log_buffer.pop(0)


def log_exception(module: str, e: Exception, level: str = "WARNING", context: str = ""):
    """???????? ? ????? emit_log + type(e).__name__ ??"""
    msg = (
        f"{context}: {type(e).__name__}: {str(e)[:100]}"
        if context
        else f"{type(e).__name__}: {str(e)[:100]}"
    )
    emit_log(level, module, msg)


def get_log_buffer() -> list[dict]:
    return _log_buffer


def get_error_logs() -> list[dict]:
    return [entry for entry in _log_buffer if entry["level"] in ("ERROR", "CRITICAL")]


def get_logs_since(index: int) -> tuple[list[dict], int]:
    """返回 index 之后的新日志 + 当前总长度(用于 SSE 增量轮询)"""
    with _log_lock:
        current_len = len(_log_buffer)
        if index >= current_len:
            return [], current_len
        return _log_buffer[index:], current_len
