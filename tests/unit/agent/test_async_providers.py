"""Provider 原生异步实现测试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import app.agent.providers.openai as openai_module
from app.agent.providers.base import ProviderConfig
from app.agent.providers.gemini import GeminiProvider
from app.agent.providers.ollama import OllamaProvider
from app.agent.providers.openai import OpenAIProvider


class _AsyncStream:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _config(model="test"):
    return ProviderConfig(name="test", api_key="k", api_url="http://provider/v1", model=model)


def test_openai_native_async_stream_and_tool_calls(monkeypatch):
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._config = _config()
    provider._reasoning_unsupported = set()
    delta = SimpleNamespace(
        content="你好",
        reasoning_content=None,
        tool_calls=[
            SimpleNamespace(
                index=0,
                id="call-1",
                function=SimpleNamespace(name="media_search", arguments='{"title":"流浪地球"}'),
            )
        ],
    )
    stream = _AsyncStream([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=stream)
    client.close = AsyncMock()
    monkeypatch.setattr(openai_module, "AsyncOpenAI", lambda **kwargs: client)
    tokens = []

    result = asyncio.run(provider.async_chat_with_tools_stream([], [], on_token=tokens.append))

    assert result.content == "你好"
    assert result.tool_calls[0].name == "media_search"
    assert result.tool_calls[0].arguments == {"title": "流浪地球"}
    assert tokens == ["你好"]


def test_ollama_native_async_stream():
    provider = OllamaProvider.__new__(OllamaProvider)
    provider._config = _config()
    provider._async_client = MagicMock()
    provider._async_client.chat = AsyncMock(
        return_value=_AsyncStream([{"message": {"content": "你好", "tool_calls": []}}])
    )
    tokens = []

    result = asyncio.run(provider.async_chat_with_tools_stream([], [], on_token=tokens.append))

    assert result.content == "你好"
    assert tokens == ["你好"]


def test_gemini_native_async_chat():
    provider = GeminiProvider.__new__(GeminiProvider)
    provider._config = _config("gemini-test")
    provider._thinking_unsupported = set()
    provider._client = MagicMock()
    provider._client.aio.models.generate_content = AsyncMock(return_value=SimpleNamespace(text="异步回答"))

    assert asyncio.run(provider.async_chat([{"role": "user", "content": "测试"}])) == "异步回答"
