"""配置管理: 加载 + 热更新 + 环境变量覆盖。

设计依据: IMPLEMENTATION_PLAN.md §5.1, S03 §3.9 (配置加载顺序)。

优先级 (高 → 低):
    1. 环境变量 (ASHARE_X_*, *_API_KEY)
    2. config/config.yaml (可提交, 无密钥)
    3. 代码默认值

热更新: 每次 get() 检查 config.yaml 的 mtime, 变化时自动重载 (见 exp12.4)。
线程安全: 用 RLock 保护读多写少场景。

环境变量映射 (ENV_MAP): ASHARE_X_FOO_BAR -> foo.bar (嵌套 key)。
API key 约定: DEEPSEEK_API_KEY -> llm.deepseek.api_key。
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# 加载项目根目录 .env（如果不存在则静默跳过）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=True)

# 配置模块日志
logger = logging.getLogger("ashare-x.core.config")

# 默认配置文件路径: ashare-x/config/config.yaml  # noqa: ERA001
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

# 环境变量 -> 配置 key 映射 (见 .env.example)
# 命名约定: ASHARE_X_<SECTION>_<KEY> -> section.key
# 特例: <PROVIDER>_API_KEY -> llm.<provider>.api_key
ENV_MAP: dict[str, str] = {
    "ASHARE_X_MONTHLY_BUDGET_RMB": "llm.monthly_budget_rmb",
    "ASHARE_X_LANG": "log.lang",
    "ASHARE_X_EMAIL_SENDER": "email.sender",
    "ASHARE_X_EMAIL_PASSWORD": "email.password",
    "ASHARE_X_EMAIL_RECIPIENT": "email.recipient",
    "DEEPSEEK_API_KEY": "llm.deepseek.api_key",
    "DEEPSEEK_BASE_URL": "llm.deepseek.base_url",
    "DASHSCOPE_API_KEY": "llm.dashscope.api_key",
    "ZHIPU_API_KEY": "llm.zhipu.api_key",
    "TUSHARE_TOKEN": "data.tushare.token",
    "TICKFLOW_TOKEN": "data.tickflow.token",
}


class Config:
    """单例配置。线程安全的读多写少 + 基于 mtime 的热更新。

    用法:
        cfg = Config()
        budget = cfg.get("llm.monthly_budget_rmb", 100)
    """

    _instance: Config | None = None
    _lock = threading.RLock()

    def __new__(cls, *args: Any, **kwargs: Any) -> Config:
        # 单例: 显式传 config_path 时重建 (主要用于测试)
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False  # type: ignore[attr-defined]
        return cls._instance

    def __init__(self, config_path: Path | str | None = None) -> None:
        if getattr(self, "_initialized", False) and config_path is None:
            return
        with self._lock:
            self.config_path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
            self.last_mtime: float = 0.0
            self.data: dict[str, Any] = {}
            self._initialized = True
            self.load()

    # ── 加载 ──────────────────────────────────────────────────────
    def load(self) -> None:
        """从 YAML 加载 + 应用 env 覆盖。线程安全。"""
        with self._lock:
            if self.config_path.exists():
                try:
                    with open(self.config_path, encoding="utf-8") as f:
                        loaded = yaml.safe_load(f) or {}
                    if not isinstance(loaded, dict):
                        raise ValueError(f"配置根节点必须是 dict, 实际是 {type(loaded).__name__}")
                    self.data = loaded
                    self.last_mtime = self.config_path.stat().st_mtime
                    logger.info("配置加载成功: %s (mtime=%.3f)", self.config_path, self.last_mtime)
                    logger.debug(
                        "配置内容: %s",
                        {k: type(v).__name__ for k, v in self.data.items()},
                    )
                except (OSError, yaml.YAMLError, ValueError) as e:
                    logger.exception("加载配置失败, 保留旧值: %s (%s)", self.config_path, e)
            else:
                logger.debug("配置文件不存在, 仅用 env + 默认值: %s", self.config_path)
            self._apply_env_overrides()
            logger.debug("环境变量覆盖后: %s", {k: type(v).__name__ for k, v in self.data.items()})

    def reload_if_changed(self) -> bool:
        """若 config.yaml 的 mtime 变化则重载, 返回是否重载。"""
        if not self.config_path.exists():
            return False
        try:
            mtime = self.config_path.stat().st_mtime
        except OSError:
            return False
        if mtime > self.last_mtime:
            self.load()
            logger.info("配置已热重载: %s", self.config_path)
            return True
        return False

    # ── 读取 ──────────────────────────────────────────────────────
    def get(self, key: str, default: Any = None) -> Any:
        """按点号 key 读取嵌套配置。每次调用检查热更新。

        Args:
            key: 点号分隔的路径, 如 "llm.deep_think.model"
            default: key 不存在时的返回值
        """
        self.reload_if_changed()
        with self._lock:
            value: Any = self.data
            for part in key.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value if value is not None else default

    # ── env 覆盖 ──────────────────────────────────────────────────
    def _apply_env_overrides(self) -> None:
        """把 ENV_MAP 中的非空 env 写入 self.data (覆盖 yaml)。"""
        for env_key, config_key in ENV_MAP.items():
            env_val = os.environ.get(env_key)
            if env_val is not None and env_val != "":
                self._set_nested(config_key, _coerce(env_val))

    def _set_nested(self, key: str, value: Any) -> None:
        parts = key.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                return
        node[parts[-1]] = value

    # ── 测试辅助 ──────────────────────────────────────────────────
    @classmethod
    def reset(cls) -> None:
        """重置单例 (仅供测试)。"""
        with cls._lock:
            cls._instance = None


def _coerce(val: str) -> Any:
    """把 env 字符串尽量转成合适的 Python 类型 (int/float/bool/str)。"""
    low = val.lower()
    if low in ("true", "yes", "1"):
        return True
    if low in ("false", "no", "0"):
        return False
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val


def get_config(config_path: Path | str | None = None) -> Config:
    """获取单例 Config 的便捷函数。"""
    return Config(config_path)
