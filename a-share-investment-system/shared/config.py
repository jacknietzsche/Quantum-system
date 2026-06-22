"""统一配置管理 — 系统环境变量 > .env > config.yaml > config.json"""

from __future__ import annotations

import json
import os
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.join(_PROJECT_ROOT, "config")
_ENV_FILE = os.path.join(_CONFIG_DIR, ".env")


class Config:
    """单例配置管理器"""

    _instance: Config | None = None

    def __new__(cls) -> Config:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._loaded = True
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        # 1. Load .env -> os.environ (lowest priority env source)
        if os.path.exists(_ENV_FILE):
            with open(_ENV_FILE, encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

        # 2. Load config.yaml as base
        yaml_path = os.path.join(_CONFIG_DIR, "config.yaml")
        if os.path.exists(yaml_path):
            try:
                import yaml

                with open(yaml_path, encoding="utf-8") as f:
                    self._data = yaml.safe_load(f) or {}
            except ImportError:
                self._data = {}

        # 3. Merge config.json (legacy, lower priority than yaml)
        # NOTE: config.json is deprecated. Please migrate settings to config/config.yaml.
        # config.json will be removed in a future version.
        json_path = os.path.join(_PROJECT_ROOT, "config.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    json_data = json.load(f)
                for k, v in json_data.items():
                    if k not in self._data:
                        self._data[k] = v
            except (OSError, json.JSONDecodeError):
                # 配置文件读取失败,回退到环境变量与默认值
                pass

        # 4. Override with env vars (highest priority)
        for key in ("MODE", "DB_PATH", "LOG_LEVEL", "PORT"):
            env_val = os.environ.get(key)
            if env_val:
                self._data[key.lower()] = env_val

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val: Any = self._data
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return default
        return val if val is not None else default

    def get_model(self, role: str = "primary") -> dict:
        # 优先从 config.yaml llm.model_roles 读取
        llm_cfg = self._data.get("llm", {})
        if isinstance(llm_cfg, dict):
            model_roles = llm_cfg.get("model_roles", {})
            if isinstance(model_roles, dict):
                provider_model = model_roles.get(role, "")
                if provider_model:
                    if ":" in provider_model:
                        provider, model = provider_model.split(":", 1)
                    else:
                        provider, model = "deepseek", provider_model
                    return {"provider": provider, "model": model}

        # 降级到 config.json legacy models 路径
        models = self._data.get("models", {})
        if isinstance(models, dict):
            provider_model = models.get(role, "")
            if provider_model:
                if ":" in provider_model:
                    provider, model = provider_model.split(":", 1)
                else:
                    provider, model = "deepseek", provider_model
                return {"provider": provider, "model": model}

        # 最终硬编码默认值
        defaults = {
            "primary": "siliconflow:deepseek-ai/DeepSeek-R1",
            "secondary": "chatanywhere:gpt-4o",
            "validator": "juguang:claude-opus-4-6",
            "fallback": "deepseek:deepseek-v4-pro",
        }
        provider_model = defaults.get(role, "deepseek:deepseek-v4-pro")
        if ":" in provider_model:
            provider, model = provider_model.split(":", 1)
        else:
            provider, model = "deepseek", provider_model
        return {"provider": provider, "model": model}

    def get_api_key(self, provider: str) -> str:
        env_key = f"{provider.upper()}_API_KEY"
        if env_key in os.environ:
            return os.environ[env_key]
        api_keys = self._data.get("api_keys", {})
        return str(api_keys.get(f"{provider}_api_key", "")) if isinstance(api_keys, dict) else ""

    def get_base_url(self, provider: str) -> str:
        # 优先从 config.yaml llm.providers 读取
        llm_cfg = self._data.get("llm", {})
        if isinstance(llm_cfg, dict):
            providers = llm_cfg.get("providers", {})
            if isinstance(providers, dict):
                provider_cfg = providers.get(provider, {})
                if isinstance(provider_cfg, dict):
                    url = provider_cfg.get("base_url", "")
                    if url:
                        return str(url)
        # 降级到 config.json legacy 路径
        api_keys = self._data.get("api_keys", {})
        return str(api_keys.get(f"{provider}_base_url", "")) if isinstance(api_keys, dict) else ""

    def get_email_config(self) -> dict:
        import os

        notification = self._data.get("notification", {})
        if not notification:
            notification = self._data.get("alert", {})
        sender = notification.get("email_sender", "") or os.environ.get("QQ_EMAIL_SENDER", "")
        password = notification.get("email_password", "") or os.environ.get(
            "QQ_EMAIL_AUTH_CODE", ""
        )
        receivers_raw = notification.get("email_receivers", [])
        if not receivers_raw:
            receivers_str = os.environ.get("QQ_EMAIL_RECEIVERS", "")
            receivers = (
                [r.strip() for r in receivers_str.split(",") if r.strip()] if receivers_str else []
            )
        else:
            receivers = (
                receivers_raw
                if isinstance(receivers_raw, list)
                else [r.strip() for r in str(receivers_raw).split(",")]
            )
        return {
            "sender": sender,
            "password": password,
            "receivers": receivers,
            "sender_name": notification.get("email_sender_name", "A股智能投研系统"),
        }

    def get_mode(self) -> str:
        env_mode = os.environ.get("MODE")
        if env_mode:
            return env_mode
        return str(self._data.get("mode", "balanced"))

    def get_itick(self) -> dict:
        tickflow = self._data.get("tickflow", {})
        if not isinstance(tickflow, dict):
            tickflow = {}
        return {
            "api_key": os.environ.get("TICKFLOW_API_KEY") or str(tickflow.get("api_key", "")),
            "base_url": str(tickflow.get("base_url", "https://api.tickflow.com")),
        }

    def get_scheduler(self) -> dict:
        scheduler = self._data.get(
            "scheduler",
            {
                "enabled": True,
                "daily_report_hour": 17,
                "daily_report_minute": 0,
                "screening_hour": 18,
                "screening_minute": 0,
            },
        )
        return scheduler if isinstance(scheduler, dict) else {}


    def get_notification(self) -> dict:
        notification = self._data.get("notification", {}) or self._data.get("alert", {})
        return {
            "enabled": notification.get("enabled", True),
            "email": bool(
                notification.get("email_sender", "") and notification.get("email_password", "")
            ),
            "wechat": bool(notification.get("wechat_key", "")),
        }

    @property
    def data(self) -> dict:
        return self._data


# Global instance
config = Config()
