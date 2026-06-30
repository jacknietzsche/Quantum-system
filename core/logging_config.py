"""
core.logging_config -- 统一日志配置
===================================
所有模块通过 get_logger(__name__) 获取 logger，
配置由 setup_logging() 统一控制。

用法:
    # 入口脚本中调用一次
    from core.logging_config import setup_logging, get_logger
    setup_logging()
    logger = get_logger(__name__)

    # 库模块中只获取 logger
    from core.logging_config import get_logger
    logger = get_logger(__name__)
"""

import logging
import sys
from pathlib import Path
from typing import Optional

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_initialized = False


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    log_dir: str = "logs",
) -> None:
    """初始化根 logger（幂等，多次调用不会重复添加 handler）。

    Args:
        level: 日志级别，默认 INFO
        log_file: 可选，日志文件名（写入 log_dir 目录下）
        log_dir: 日志文件目录，默认 logs/
    """
    global _initialized
    if _initialized:
        return

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(Path(log_dir) / log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger。入口脚本应先调用 setup_logging()。"""
    return logging.getLogger(name)
