"""TMDB 客户端热重载 — 必须在原实例上 reset，替换实例不生效（组件持有同一实例）."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from app.di.context import AppContext
from app.infrastructure.cache_system.metadata_cache import MetadataCache
from app.media.lookup import tmdb_client as tmdb_client_module
from app.media.lookup.tmdb_client import TmdbClient
from app.services.config_reloader import ConfigReloader


class _FakeSettings:
    """仅覆盖 app/media 节点的最小 settings 替身"""

    def __init__(self, app: dict, media: dict | None = None):
        self._app = app
        self._media = media or {}

    def get(self, node=None):
        if node == "app":
            return self._app
        if node == "media":
            return self._media
        return {}


class TestTmdbClientReload:
    def test_reload_resets_in_place_and_rebuilds_client(self):
        """网页保存 API Key 后：原实例被 reset，search 可用且实例身份不变"""
        with patch.object(tmdb_client_module, "settings", _FakeSettings({})):
            ctx = SimpleNamespace(
                tmdb_client=TmdbClient(),
                knowledge_ingestor=None,
                conversation_store=None,
            )
        client = ctx.tmdb_client
        assert client.search is None  # 启动时未配置 Key

        reloader = ConfigReloader(cast("AppContext", ctx))
        with patch.object(tmdb_client_module, "settings", _FakeSettings({"rmt_tmdbkey": "test-key"})):
            reloader._reset_tmdb_client()

        assert ctx.tmdb_client is client  # 未替换实例，已装配组件可见
        assert client.search is not None
        assert client.tmdb is not None
        assert client.tmdb.api_key == "test-key"

    def test_reset_clears_client_when_key_removed(self):
        """清空 API Key 后 reset 不应继续沿用旧客户端"""
        with patch.object(tmdb_client_module, "settings", _FakeSettings({"rmt_tmdbkey": "test-key"})):
            client = TmdbClient()
        assert client.search is not None

        with patch.object(tmdb_client_module, "settings", _FakeSettings({})):
            client.reset()

        assert client.search is None
        assert client.tmdb is None

    def test_reset_clears_lookup_negative_cache(self):
        """Key 缺失期间写入的"未找到"负缓存必须随重载清理"""
        lookup_cache = MetadataCache(prefix="lookup")
        lookup_cache.set("some title||||", False, ttl=3600)
        assert lookup_cache.get("some title||||") is False

        with patch.object(tmdb_client_module, "settings", _FakeSettings({"rmt_tmdbkey": "test-key"})):
            TmdbClient().reset()

        assert lookup_cache.get("some title||||") is None
