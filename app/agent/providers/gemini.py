"""Google Gemini 提供商"""

from typing import Any

from google import genai
from google.genai import types

import log
from app.agent.providers.base import BaseProvider, ProviderConfig


class GeminiProvider(BaseProvider):
    """Google Gemini 提供商"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = genai.Client(api_key=config.api_key)

    def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        response_format: type | None = None,
    ) -> Any:
        contents = []
        for m in messages:
            if m.get("role") == "user":
                contents.append(m.get("content", ""))

        config = types.GenerateContentConfig(
            response_mime_type="application/json" if response_format else None,
            temperature=temperature,
        )

        resp = self._client.models.generate_content(
            model=self._config.model,
            contents=contents,
            config=config,
        )
        return resp.text

    def is_available(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            models = self._client.models.list()
            return [m.name for m in models]
        except Exception as e:
            log.warn(f"【GeminiProvider】查询模型列表失败: {e}")
            return []
