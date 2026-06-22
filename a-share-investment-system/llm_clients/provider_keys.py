"""Provider 别名规范化 — 参考 TradingAgents-CN/provider_keys.py

处理中文提供商名称和别名映射.
"""

from __future__ import annotations

# 别名映射
_ALIASES = {
    "dashscope": "qwen",
    "alibaba": "qwen",
    "阿里百炼": "qwen",
    "百炼": "qwen",
    "zhipu": "glm",
    "智谱": "glm",
    "智谱ai": "glm",
    "siliconflow": "siliconflow",
    "moonshot": "moonshot",
    "chatanywhere": "chatanywhere",
    "juguang": "juguang",
    "openai": "openai",
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "google": "google",
    "openrouter": "openrouter",
    "aihubmix": "aihubmix",
    "ollama": "ollama",
    "qianfan": "qianfan",
    "custom_openai": "custom_openai",
}

# Provider 默认配置: (base_url, api_key_env)
_PROVIDER_CONFIG = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4/", "ZHIPU_API_KEY"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY"),
    "moonshot": ("https://api.moonshot.cn/v1", "MOONSHOT_API_KEY"),
    "chatanywhere": ("https://api.chatanywhere.tech/v1", "CHATANYWHERE_API_KEY"),
    "juguang": ("https://api.juguang.ai/v1", "JUGUANG_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "aihubmix": ("https://aihubmix.com/v1", "AIHUBMIX_API_KEY"),
    "qianfan": ("https://qianfan.baidubce.com/v2", "QIANFAN_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "anthropic": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
    "google": ("https://generativelanguage.googleapis.com/v1beta", "GOOGLE_API_KEY"),
}


def normalize_provider_key(provider: str) -> str:
    """规范化提供商名称"""
    if provider is None:
        return ""
    raw = str(provider).strip()
    if not raw:
        return ""
    lowered = raw.lower()
    return _ALIASES.get(lowered, lowered)


def env_key_for_provider(provider: str) -> str:
    """获取提供商的环境变量名"""
    key = normalize_provider_key(provider)
    config = _PROVIDER_CONFIG.get(key)
    if config:
        return config[1] or ""
    return ""


def default_backend_url(provider: str) -> str:
    """获取提供商的默认端点 URL"""
    key = normalize_provider_key(provider)
    config = _PROVIDER_CONFIG.get(key)
    if config:
        return config[0] or ""
    return ""
