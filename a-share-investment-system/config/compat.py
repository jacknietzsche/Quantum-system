"""
配置兼容桥接层 — 让旧模块从新配置源(config/config.yaml + .env)读取数据

旧模块(multi_model_voter.py, data_bus.py, web_app.py 等)原本读取 config.json,
此模块提供等效接口,数据来自 config/config.yaml + 环境变量。

用法:
    from config.compat import load_legacy_config
    cfg = load_legacy_config()
    api_keys = cfg["api_keys"]
    models = cfg["models"]
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 加载 .env
try:
    from dotenv import load_dotenv

    _env = Path(__file__).parent / ".env"
    if _env.exists():
        load_dotenv(_env, override=False)
except ImportError:
    # dotenv 是可选依赖,未安装时直接使用环境变量
    pass

# 加载 config.yaml
import yaml

_cfg_path = Path(__file__).parent / "config.yaml"
_config_data: dict[str, Any] = {}
if _cfg_path.exists():
    with open(_cfg_path, encoding="utf-8") as f:
        _config_data = yaml.safe_load(f) or {}


def load_legacy_config() -> dict[str, Any]:
    """生成兼容 config.json 格式的配置字典"""
    providers = _config_data.get("llm", {}).get("providers", {})
    roles = _config_data.get("llm", {}).get("model_roles", {})

    # 构建 api_keys 字典(从环境变量读取)
    api_keys = {}
    provider_env_map = {
        "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
        "siliconflow": ("SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL"),
        "chatanywhere": ("CHATANYWHERE_API_KEY", "CHATANYWHERE_BASE_URL"),
        "juguang": ("JUGUANG_API_KEY", "JUGUANG_BASE_URL"),
        "cherryin": ("CHERRYIN_API_KEY", "CHERRYIN_BASE_URL"),
    }
    for provider, (key_env, url_env) in provider_env_map.items():
        api_key = os.environ.get(key_env, "")
        base_url = os.environ.get(url_env, "")
        if not base_url and provider in providers:
            base_url = providers[provider].get("base_url", "")
        if api_key:
            api_keys[f"{provider}_api_key"] = api_key
        if base_url:
            api_keys[f"{provider}_base_url"] = base_url

    tickflow_key = os.environ.get("TICKFLOW_API_KEY", "")
    if tickflow_key:
        api_keys["tickflow_api_key"] = tickflow_key

    # 构建 models 字典
    models = {}
    role_map = {"primary": "主力", "secondary": "辅助", "validator": "验证", "fallback": "备选"}
    for eng, chn in role_map.items():
        if eng in roles:
            models[chn] = roles[eng]

    # 构建 model_registry
    model_registry = {}
    for provider, cfg in providers.items():
        if "models" in cfg:
            model_registry[provider] = cfg["models"]

    # 构建 alert 字典
    email_cfg = _config_data.get("notification", {}).get("email", {})

    return {
        "models": models,
        "model_registry": model_registry,
        "api_keys": api_keys,
        "alert": {
            "channels": ["console", "email"],
            "email_sender": os.environ.get("QQ_EMAIL_SENDER", email_cfg.get("sender", "")),
            "email_password": os.environ.get("QQ_EMAIL_AUTH_CODE", email_cfg.get("auth_code", "")),
            "email_receivers": [
                r.strip() for r in os.environ.get("QQ_EMAIL_RECEIVERS", "").split(",") if r.strip()
            ]
            or ["2147139097@qq.com"],
            "email_sender_name": "A股智能投研系统",
        },
        "data_ttl": _config_data.get("data", {}).get(
            "ttl",
            {
                "realtime_quote": 300,
                "kline_daily": "market_close",
                "north_flow": 300,
                "market_breadth": 300,
                "index_quote": 300,
                "hot_stocks": 300,
                "company_fundamentals": 604800,
                "industry_info": 604800,
            },
        ),
    }


# 单例缓存
_cached: dict[str, Any] | None = None


def get_legacy_config() -> dict[str, Any]:
    """获取兼容配置(单例)"""
    global _cached  # noqa: PLW0603
    if _cached is None:
        _cached = load_legacy_config()
    return _cached


def get_api_key(provider: str) -> str:
    """获取 API 密钥的兼容函数"""
    cfg = get_legacy_config()
    api_keys = cfg.get("api_keys", {})
    return str(api_keys.get(f"{provider}_api_key", "")) if isinstance(api_keys, dict) else ""


def get_base_url(provider: str) -> str:
    """获取 base URL 的兼容函数"""
    cfg = get_legacy_config()
    api_keys = cfg.get("api_keys", {})
    return str(api_keys.get(f"{provider}_base_url", "")) if isinstance(api_keys, dict) else ""
