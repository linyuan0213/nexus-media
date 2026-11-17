"""Google Gemini 提供商"""

from __future__ import annotations

import warnings
from typing import Any

# Python 3.15+ 延迟加载可选 Gemini SDK；旧版本忽略。
__lazy_modules__ = {"google", "google.genai", "google.genai.errors"}

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from google import genai  # type: ignore  # noqa: PGH003
    from google.genai import types
    from google.genai.errors import ClientError

import log
from app.agent.providers.base import (
    _TOOL_PROMPT,
    BaseEmbeddingProvider,
    BaseProvider,
    ChatToolResponse,
    LLMThrottle,
    ProviderConfig,
    ReasoningConfig,
)
from app.utils.json_utils import JsonUtils

# 推理强度 → thinkingBudget（token 预算；0 = 关闭思考）
_THINKING_BUDGET = {"low": 1024, "high": 4096, "max": 16384}


def _build_http_options(config: ProviderConfig) -> types.HttpOptions | None:
    """组装 HttpOptions：自定义 base_url（中转/反代）、代理；timeout 单位毫秒

    base_url 需剥离 /v1beta、/v1 后缀 — SDK 会自行拼接 api_version，重复会导致 404
    """
    if not (config.api_url or config.proxy):
        return None
    base_url = (config.api_url or "").rstrip("/").removesuffix("/v1beta").removesuffix("/v1") or None
    return types.HttpOptions(
        base_url=base_url,
        timeout=config.timeout * 1000 if config.timeout else None,
        client_args={"proxy": config.proxy} if config.proxy else None,
    )


class GeminiProvider(BaseProvider):
    """Google Gemini 提供商"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = genai.Client(api_key=config.api_key, http_options=_build_http_options(config))
        # 已确认不支持 thinking_config 的模型（剥离重试成功时记录）
        self._thinking_unsupported: set[str] = set()

    def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        response_format: type | None = None,
        reasoning: ReasoningConfig | None = None,
    ) -> Any:
        contents = []
        for m in messages:
            if m.get("role") == "user":
                contents.append(m.get("content", ""))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            response_mime_type="application/json" if response_format else None,
            temperature=temperature,
        )
        if reasoning and self._config.model not in self._thinking_unsupported:
            budget = 0 if not reasoning.enabled else _THINKING_BUDGET.get(reasoning.effort, 4096)
            config.thinking_config = types.ThinkingConfig(thinking_budget=budget)

        try:
            resp = LLMThrottle.call(
                self._client.models.generate_content,
                model=self._config.model,
                contents=contents,
                config=config,
            )
        except ClientError as e:
            # 模型不支持 thinking_config 时剥离后重试一次（并记忆该模型）
            if e.code == 400 and config.thinking_config and "thinking" in str(e).lower():
                log.debug("[GeminiProvider]模型不支持 thinking_config，剥离后重试")
                config.thinking_config = None
                self._thinking_unsupported.add(self._config.model)
                resp = LLMThrottle.call(
                    self._client.models.generate_content,
                    model=self._config.model,
                    contents=contents,
                    config=config,
                )
            else:
                raise
        return resp.text

    async def async_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        response_format: type | None = None,
        reasoning: ReasoningConfig | None = None,
    ) -> Any:
        """原生异步 Gemini 对话。"""
        contents = [m.get("content", "") for m in messages if m.get("role") == "user"]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            response_mime_type="application/json" if response_format else None,
            temperature=temperature,
        )
        if reasoning and self._config.model not in self._thinking_unsupported:
            budget = 0 if not reasoning.enabled else _THINKING_BUDGET.get(reasoning.effort, 4096)
            config.thinking_config = types.ThinkingConfig(thinking_budget=budget)
        try:
            resp = await LLMThrottle.call_async(
                self._client.aio.models.generate_content,
                model=self._config.model,
                contents=contents,
                config=config,
            )
        except ClientError as e:
            if e.code == 400 and config.thinking_config and "thinking" in str(e).lower():
                config.thinking_config = None
                self._thinking_unsupported.add(self._config.model)
                resp = await LLMThrottle.call_async(
                    self._client.aio.models.generate_content,
                    model=self._config.model,
                    contents=contents,
                    config=config,
                )
            else:
                raise
        return resp.text

    async def async_chat_with_tools_stream(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        on_token: Any = None,
        on_reasoning: Any = None,
        reasoning: ReasoningConfig | None = None,
    ) -> ChatToolResponse:
        prompt = _TOOL_PROMPT.replace("{tools}", JsonUtils.dumps(tools, ensure_ascii=False, indent=2))
        content = await self.async_chat(
            messages=messages,
            system_prompt=prompt,
            temperature=temperature,
            reasoning=reasoning,
        )
        response = self._parse_prompt_tool_response(content)
        if on_token and response.content:
            on_token(response.content)
        return response

    def is_available(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            models = self._client.models.list()
            return [name for m in models if (name := m.name) is not None]
        except Exception as e:
            log.warn(f"[GeminiProvider]查询模型列表失败: {e}")
            return []


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Google Gemini Embedding 提供商（gemini-embedding 系列）"""

    def __init__(self, config: ProviderConfig, model: str):
        super().__init__(config, model)
        self._client = genai.Client(api_key=config.api_key, http_options=_build_http_options(config))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        contents: list[Any] = [types.Part.from_text(text=t) for t in texts]
        resp = LLMThrottle.call(self._client.models.embed_content, model=self._model, contents=contents)
        vectors = [list(map(float, e.values)) for e in resp.embeddings or [] if e.values]
        if vectors and self._dimension is None:
            self._dimension = len(vectors[0])
        return vectors

    def is_available(self) -> bool:
        try:
            self.embed(["health check"])
            return True
        except Exception as e:
            log.warn(f"[GeminiEmbeddingProvider]不可用: {e}")
            return False
