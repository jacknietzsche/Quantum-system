"""结构化日志管理器 — 参考 TradingAgents-CN/logging_manager.py

关键特性:
1. 彩色终端输出
2. JSON 结构化日志 (生产环境)
3. 文件轮转
4. 会话追踪
5. Token 使用和成本记录
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Any, ClassVar


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # 青色
        "INFO": "\033[32m",  # 绿色
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 红色
        "CRITICAL": "\033[35m",  # 紫色
        "RESET": "\033[0m",
    }

    def format(self, record):
        if hasattr(record, "levelname") and record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
            )
        return super().format(record)


class StructuredFormatter(logging.Formatter):
    """JSON 结构化日志格式化器"""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        # 添加额外字段
        for field in ("session_id", "stock_code", "analysis_type", "cost", "tokens"):
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)
        return json.dumps(log_entry, ensure_ascii=False)


class LoggingManager:
    """统一日志管理器"""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or self._default_config()
        self.loggers: dict[str, logging.Logger] = {}
        self._setup()

    def _default_config(self) -> dict[str, Any]:
        log_level = os.getenv("ASHARE_LOG_LEVEL", "INFO").upper()
        log_dir = os.getenv("ASHARE_LOG_DIR", "logs")
        return {
            "level": log_level,
            "console": {
                "enabled": True,
                "colored": True,
                "level": log_level,
            },
            "file": {
                "enabled": True,
                "level": "DEBUG",
                "max_size_mb": 10,
                "backup_count": 5,
                "directory": log_dir,
            },
            "structured": {
                "enabled": False,
                "level": "INFO",
                "directory": log_dir,
            },
            "suppress": {
                "urllib3": "WARNING",
                "requests": "WARNING",
                "matplotlib": "WARNING",
                "httpx": "WARNING",
            },
        }

    def _setup(self):
        """配置日志系统"""
        root = logging.getLogger()
        root.setLevel(self.config.get("level", "INFO"))

        # 清除已有 handler
        root.handlers.clear()

        # Console handler
        if self.config.get("console", {}).get("enabled", True):
            console = logging.StreamHandler(sys.stdout)
            if self.config["console"].get("colored", True):
                console.setFormatter(
                    ColoredFormatter(
                        "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
                        datefmt="%H:%M:%S",
                    )
                )
            else:
                console.setFormatter(
                    logging.Formatter(
                        "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
                        datefmt="%H:%M:%S",
                    )
                )
            console.setLevel(self.config["console"].get("level", "INFO"))
            root.addHandler(console)

        # File handler
        if self.config.get("file", {}).get("enabled", True):
            log_dir = self.config["file"].get("directory", "logs")
            os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "ashare.log"),
                maxBytes=self.config["file"].get("max_size_mb", 10) * 1024 * 1024,
                backupCount=self.config["file"].get("backup_count", 5),
                encoding="utf-8",
            )
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(name)-20s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
                )
            )
            file_handler.setLevel(self.config["file"].get("level", "DEBUG"))
            root.addHandler(file_handler)

            # Error file handler
            error_handler = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "error.log"),
                maxBytes=self.config["file"].get("max_size_mb", 10) * 1024 * 1024,
                backupCount=self.config["file"].get("backup_count", 5),
                encoding="utf-8",
            )
            error_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(name)-20s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
                )
            )
            error_handler.setLevel("WARNING")
            root.addHandler(error_handler)

        # Suppress noisy loggers
        for logger_name, level_name in self.config.get("suppress", {}).items():
            level = getattr(logging, level_name.upper(), logging.WARNING)
            logging.getLogger(logger_name).setLevel(level)

    def get_logger(self, name: str) -> logging.Logger:
        """获取命名 logger"""
        if name not in self.loggers:
            self.loggers[name] = logging.getLogger(f"ashare.{name}")
        return self.loggers[name]

    def log_analysis_start(
        self, logger: logging.Logger, stock_code: str, analysis_type: str, session_id: str = ""
    ):
        """记录分析开始"""
        logger.info(
            "开始分析 - 股票: %s, 类型: %s",
            stock_code,
            analysis_type,
            extra={
                "stock_code": stock_code,
                "analysis_type": analysis_type,
                "session_id": session_id,
                "event_type": "analysis_start",
            },
        )

    def log_analysis_complete(
        self,
        logger: logging.Logger,
        stock_code: str,
        analysis_type: str,
        duration: float,
        session_id: str = "",
        cost: float = 0,
    ):
        """记录分析完成"""
        logger.info(
            "分析完成 - 股票: %s, 耗时: %.2fs, 成本: %.4f",
            stock_code,
            duration,
            cost,
            extra={
                "stock_code": stock_code,
                "analysis_type": analysis_type,
                "session_id": session_id,
                "duration": duration,
                "cost": cost,
                "event_type": "analysis_complete",
            },
        )

    def log_module_error(
        self,
        logger: logging.Logger,
        module_name: str,
        stock_code: str,
        error: str,
        duration: float = 0,
        session_id: str = "",
    ):
        """记录模块错误"""
        logger.error(
            "模块错误 - %s - 股票: %s, 耗时: %.2fs, 错误: %s",
            module_name,
            stock_code,
            duration,
            error,
            extra={
                "module_name": module_name,
                "stock_code": stock_code,
                "session_id": session_id,
                "duration": duration,
                "error": error,
                "event_type": "module_error",
            },
            exc_info=True,
        )

    def log_token_usage(
        self,
        logger: logging.Logger,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        session_id: str = "",
    ):
        """记录 Token 使用"""
        logger.info(
            "Token使用 - %s/%s: 输入=%d, 输出=%d, 成本=%.6f",
            provider,
            model,
            input_tokens,
            output_tokens,
            cost,
            extra={
                "provider": provider,
                "model": model,
                "tokens": {"input": input_tokens, "output": output_tokens},
                "cost": cost,
                "session_id": session_id,
                "event_type": "token_usage",
            },
        )


# ─── 全局单例 ───
_manager: LoggingManager | None = None


def get_logging_manager() -> LoggingManager:
    global _manager  # noqa: PLW0603
    if _manager is None:
        _manager = LoggingManager()
    return _manager


def get_logger(name: str = "default") -> logging.Logger:
    """获取命名 logger (便捷函数)"""
    return get_logging_manager().get_logger(name)
