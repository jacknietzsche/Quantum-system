"""Anthropic Claude 客户端"""

import logging
from typing import Any

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


class AnthropicClient(BaseLLMClient):
    def __init__(
        self, model: str, base_url: str | None = None, api_key: str | None = None, **kwargs
    ):
        super().__init__(model, base_url, **kwargs)
        self.api_key = api_key
        self._kwargs = kwargs

    def get_llm(self) -> Any:
        if self._llm is None:
            from langchain_anthropic import ChatAnthropic

            kwargs: dict[str, Any] = {
                "model": self.model,
                "timeout": self._kwargs.get("timeout", 60),
                "max_retries": self._kwargs.get("max_retries", 2),
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            if "temperature" in self._kwargs:
                kwargs["temperature"] = self._kwargs["temperature"]
            if "max_tokens" in self._kwargs:
                kwargs["max_tokens"] = self._kwargs["max_tokens"]

            self._llm = ChatAnthropic(**kwargs)
            logger.debug("Anthropic client: model=%s", self.model)
        return self._llm
