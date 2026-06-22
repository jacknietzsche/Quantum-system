"""LLM 客户端工厂 — 参考 TradingAgents-CN/factory.py 改进

关键改进:
1. Provider 别名处理 (阿里百炼→qwen, 智谱→glm)
2. 懒加载 provider 模块
3. 支持自定义端点
"""

import logging

from .base_client import BaseLLMClient
from .provider_keys import normalize_provider_key

logger = logging.getLogger(__name__)

# Provider 别名 (已在 provider_keys 中定义,此处保留用于 factory 内部引用)
_PROVIDER_ALIASES = {
    "dashscope": "qwen",
    "alibaba": "qwen",
    "阿里百炼": "qwen",
    "百炼": "qwen",
    "zhipu": "glm",
    "智谱": "glm",
    "siliconflow": "siliconflow",
}

# OpenAI 兼容提供商
_OPENAI_COMPATIBLE = {
    "openai",
    "deepseek",
    "qwen",
    "glm",
    "qianfan",
    "openrouter",
    "aihubmix",
    "ollama",
    "custom_openai",
    "siliconflow",
    "moonshot",
    "chatanywhere",
    "juguang",
    "groq",
    "together",
    "fireworks",
}


def create_llm_client(
    provider: str,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    **kwargs,
) -> BaseLLMClient:
    """创建 LLM 客户端

    Args:
        provider: 提供商名称 (支持中文别名)
        model: 模型名称
        base_url: API 端点 URL (可选,有默认值)
        api_key: API 密钥 (可选,从环境变量读取)
        **kwargs: 额外参数

    Returns:
        BaseLLMClient 实例
    """
    provider_normalized = normalize_provider_key(provider)

    if provider_normalized in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAICompatibleClient

        return OpenAICompatibleClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            provider=provider_normalized,
            **kwargs,
        )

    if provider_normalized in ("anthropic", "claude"):
        from .anthropic_client import AnthropicClient

        return AnthropicClient(model, base_url, api_key=api_key, **kwargs)

    if provider_normalized in ("google", "gemini"):
        from .google_client import GoogleClient

        return GoogleClient(model, base_url, api_key=api_key, **kwargs)

    if provider_normalized == "azure":
        from .azure_client import AzureClient

        return AzureClient(model, base_url, api_key=api_key, **kwargs)

    raise ValueError(
        f"Unsupported LLM provider: {provider} (normalized: {provider_normalized}). "
        f"Supported: {', '.join(sorted(_OPENAI_COMPATIBLE))}, anthropic, google, azure"
    )


def get_client_for_role(role: str = "primary") -> BaseLLMClient:
    """根据角色获取 LLM 客端 (从配置读取)

    角色映射:
    - primary: 主力模型 (深度分析)
    - secondary: 辅助模型 (快速任务)
    - validator: 验证模型 (风控审核)
    - fallback: 降级模型
    """
    from shared.config import config

    model_info = config.get_model(role)
    provider = model_info.get("provider", "deepseek")
    model = model_info.get("model", "deepseek-chat")
    api_key = config.get_api_key(provider)
    base_url = config.get_base_url(provider)

    return create_llm_client(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
