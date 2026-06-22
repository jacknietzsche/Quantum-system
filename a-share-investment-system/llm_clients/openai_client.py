"""OpenAI 兼容 LLM 客户端 — 参考 TradingAgents-CN 改进

关键改进:
1. NormalizedChatOpenAI: 规范化不同提供商的 content blocks
2. provider_keys 集成: 自动解析别名和默认配置
3. validate_model: 模型验证
"""

import logging
import os
from typing import Any

from .base_client import BaseLLMClient, normalize_content
from .provider_keys import default_backend_url, env_key_for_provider, normalize_provider_key

logger = logging.getLogger(__name__)


class NormalizedChatOpenAI:
    """ChatOpenAI 包装器 — 规范化 content blocks

    某些提供商 (如 Anthropic, Google) 返回的 content 是 list[dict] 格式,
    此包装器将其统一转为纯文本.
    """

    def __init__(self, **kwargs):
        from langchain_openai import ChatOpenAI

        self._inner = ChatOpenAI(**kwargs)

    def invoke(self, input, config=None, **kwargs):
        result = self._inner.invoke(input, config, **kwargs)
        return normalize_content(result)

    def bind_tools(self, tools):
        self._inner = self._inner.bind_tools(tools)
        return self

    def with_structured_output(self, schema):
        try:
            self._inner = self._inner.with_structured_output(schema)
            return self
        except (NotImplementedError, AttributeError):
            return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


# 可传递给 ChatOpenAI 的参数
_PASSTHROUGH_KWARGS = (
    "temperature",
    "max_tokens",
    "timeout",
    "max_retries",
    "callbacks",
    "http_client",
    "http_async_client",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
)


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容客户端

    通过 langchain_openai.ChatOpenAI 统一调用所有兼容 API.
    自动处理:
    - Provider 别名 (阿里百炼→qwen, 智谱→glm)
    - 默认端点 URL
    - 环境变量 API key 查找
    - Content block 规范化
    """

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = normalize_provider_key(provider)
        self.api_key = api_key
        self._extra_kwargs = kwargs

    def _resolve_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        return default_backend_url(self.provider)

    def _resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        # 按提供商查找环境变量
        env_name = env_key_for_provider(self.provider)
        if env_name:
            key = os.environ.get(env_name, "")
            if key:
                return key
        # 降级: 通用环境变量  # noqa: ERA001
        for name in ("OPENAI_API_KEY", "LLM_API_KEY"):
            key = os.environ.get(name, "")
            if key:
                return key
        # Ollama 不需要 key
        if self.provider == "ollama":
            return "ollama"
        return ""

    def get_llm(self) -> Any:
        base_url = self._resolve_base_url()
        api_key = self._resolve_api_key()

        llm_kwargs: dict[str, Any] = {
            "model": self.model,
            "base_url": base_url,
        }
        if api_key:
            llm_kwargs["api_key"] = api_key

        # 转发已知参数
        for k in _PASSTHROUGH_KWARGS:
            if k in self._extra_kwargs:
                llm_kwargs[k] = self._extra_kwargs[k]

        logger.debug(
            "OpenAI client: provider=%s model=%s base_url=%s",
            self.provider,
            self.model,
            base_url,
        )

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """简单模型验证 — 已知模型列表检查"""
        known_models = {
            "openai": {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-5", "o1", "o3"},
            "deepseek": {"deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro"},
            "qwen": {"qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"},
            "glm": {"glm-4", "glm-4-flash", "glm-4v"},
            "siliconflow": set(),  # 太多模型,不验证
            "moonshot": {"moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"},
        }
        models = known_models.get(self.provider, set())
        if not models:
            return True  # 未知提供商,不验证
        return self.model in models
