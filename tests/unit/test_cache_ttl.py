"""专用缓存 TTL 单元测试."""

from __future__ import annotations

import time

import pytest

from app.infrastructure.cache_system.caches import (
    CategoryLoadCache,
    ConfigLoadCache,
    MediaInfoCache,
    OpenAISessionCache,
    SearchResultCache,
    SiteInfoCache,
    TokenCache,
    WordsProcessCache,
)


class TestTypedCacheTTL:
    """测试各业务缓存默认 TTL."""

    @pytest.mark.parametrize(
        ("cache_cls", "expected_ttl", "maxsize"),
        [
            (MediaInfoCache, 24 * 3600, 1000),
            (SearchResultCache, 3600, 500),
            (SiteInfoCache, 6 * 3600, 100),
            (TokenCache, 7 * 24 * 3600, 512),
            (ConfigLoadCache, 600, 1),
            (CategoryLoadCache, 600, 2),
            (OpenAISessionCache, 30 * 24 * 3600, 200),
            (WordsProcessCache, 24 * 3600, 1000),
        ],
    )
    def test_default_ttl_and_maxsize(self, cache_cls, expected_ttl, maxsize):
        cache = cache_cls()
        assert cache._adapter._default_ttl == expected_ttl
        assert cache._adapter._maxsize == maxsize

    def test_set_uses_default_ttl(self):
        cache = MediaInfoCache()
        cache.set("k", "v")
        ttl = cache._adapter.ttl("k")
        assert ttl > 0
        assert ttl <= 24 * 3600

    def test_set_accepts_custom_ttl(self):
        cache = MediaInfoCache()
        cache.set("k", "v", ttl=1)
        assert cache.get("k") == "v"
        time.sleep(1.1)
        assert cache.get("k") is None

    def test_search_result_expires(self):
        cache = SearchResultCache()
        cache.set("k", "v", ttl=1)
        assert cache.get("k") == "v"
        time.sleep(1.1)
        assert cache.get("k") is None

    def test_site_info_default_ttl(self):
        cache = SiteInfoCache()
        cache.set("k", "v")
        ttl = cache._adapter.ttl("k")
        assert 0 < ttl <= 6 * 3600
