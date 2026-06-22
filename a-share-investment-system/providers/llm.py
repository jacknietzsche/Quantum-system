"""LLM 统一调用接口"""

import requests

from shared.config import config as _cfg


class LLMCaller:
    """多模型统一调用,支持自动降级"""

    def __init__(self, config=None):
        self._cfg = _cfg or config

    def call(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict:
        """调用指定模型"""
        if ":" in model:
            provider, model_name = model.split(":", 1)
        else:
            provider, model_name = "deepseek", model

        api_key = self._cfg.get_api_key(provider)
        base_url = self._cfg.get_base_url(provider)
        if not api_key:
            return {"error": f"No API key for {provider}", "content": ""}
        if not base_url:
            base_url = f"https://api.{provider}.com/v1"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "usage": data.get("usage", {}), "model": model}
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "content": ""}
        except Exception as e:
            return {"error": str(e), "content": ""}

    def call_with_fallback(self, prompt: str, system: str | None = None, **kwargs) -> dict:
        """带降级的调用:primary → secondary → fallback"""
        roles = ["primary", "secondary", "fallback"]
        for role in roles:
            model_info = self._cfg.get_model(role)
            model = f"{model_info['provider']}:{model_info['model']}"
            result = self.call(model, prompt, system=system, **kwargs)
            if not result.get("error"):
                result["used_role"] = role
                return result
            print(f"[LLM] {role} failed: {result['error'][:80]}")
        return {"error": "All models failed", "content": ""}
