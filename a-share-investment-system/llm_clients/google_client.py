"""Google Gemini 客户端"""

import logging
from typing import Any

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


class GoogleClient(BaseLLMClient):
    def __init__(
        self, model: str, base_url: str | None = None, api_key: str | None = None, **kwargs
    ):
        super().__init__(model, base_url, **kwargs)
        self.api_key = api_key
        self._kwargs = kwargs

    def get_llm(self) -> Any:
        if self._llm is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            kwargs: dict[str, Any] = {"model": self.model}
            if self.api_key:
                kwargs["google_api_key"] = self.api_key
            if "temperature" in self._kwargs:
                kwargs["temperature"] = self._kwargs["temperature"]
            if "max_tokens" in self._kwargs:
                kwargs["max_output_tokens"] = self._kwargs["max_tokens"]

            self._llm = ChatGoogleGenerativeAI(**kwargs)
            logger.debug("Google client: model=%s", self.model)
        return self._llm
