"""Azure OpenAI 客户端"""

import logging
import os
from typing import Any

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


class AzureClient(BaseLLMClient):
    def __init__(
        self, model: str, base_url: str | None = None, api_key: str | None = None, **kwargs
    ):
        super().__init__(model, base_url, **kwargs)
        self.api_key = api_key
        self._kwargs = kwargs

    def get_llm(self) -> Any:
        if self._llm is None:
            from langchain_openai import AzureChatOpenAI

            kwargs: dict[str, Any] = {
                "azure_deployment": self.model,
                "api_version": self._kwargs.get("api_version", "2024-12-01-preview"),
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["azure_endpoint"] = self.base_url
            else:
                kwargs["azure_endpoint"] = os.environ.get("AZURE_OPENAI_ENDPOINT", "")

            self._llm = AzureChatOpenAI(**kwargs)
            logger.debug("Azure client: model=%s", self.model)
        return self._llm
