"""Ollama 本地模型提供商"""

from typing import Any

from ollama import Client

import log
from app.agent.providers.base import BaseProvider, ProviderConfig


class OllamaProvider(BaseProvider):
    """Ollama 本地模型提供商"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = Client(host=config.api_url)

    def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        response_format: type | None = None,
    ) -> Any:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        resp = self._client.chat(
            model=self._config.model,
            messages=msgs,
            options={"temperature": temperature},
        )
        return resp["message"]["content"]

    def is_available(self) -> bool:
        try:
            self._client.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            result = self._client.list()
            return [m.model for m in result.models if m.model is not None] if hasattr(result, "models") else []
        except Exception as e:
            log.warn(f"【OllamaProvider】查询模型列表失败: {e}")
            return []
