"""Base LLM client — 参考 TradingAgents-CN/base_client.py

统一接口定义 + content 规范化.
"""

import warnings
from abc import ABC, abstractmethod
from typing import Any


def normalize_content(response):
    """规范化不同提供商的 content blocks 为纯文本

    某些提供商返回 content = [{"type": "text", "text": "..."}]
    此函数将其统一为 response.content = "..."
    """
    content = getattr(response, "content", None)
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        response.content = "\n".join(t for t in texts if t)
    return response


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类

    所有提供商客户端必须实现:
    - get_llm(): 返回 langchain 兼容的 LLM 实例
    - validate_model(): 返回模型是否已知
    """

    def __init__(self, model: str, base_url: str | None = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        """获取提供商名称"""
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        """未知模型时发出警告"""
        if self.validate_model():
            return
        warnings.warn(
            f"Model '{self.model}' is not in the known model list for "
            f"provider '{self.get_provider_name()}'. Continuing anyway.",
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """返回 langchain 兼容的 LLM 实例"""
        ...

    @abstractmethod
    def validate_model(self) -> bool:
        """返回模型是否已知"""
        ...

    def invoke(self, prompt: str, **kwargs) -> str:
        """直接调用 LLM,返回文本"""
        llm = self.get_llm()
        result = llm.invoke(prompt, **kwargs)
        result = normalize_content(result)
        return result.content if hasattr(result, "content") else str(result)

    def bind_tools(self, tools: list[Any]) -> Any:
        """绑定工具"""
        llm = self.get_llm()
        return llm.bind_tools(tools)

    def with_structured_output(self, schema: Any) -> Any:
        """结构化输出绑定"""
        llm = self.get_llm()
        try:
            return llm.with_structured_output(schema)
        except (NotImplementedError, AttributeError):
            return None
