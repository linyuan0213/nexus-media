"""统一元数据缓存测试."""

from app.infrastructure.cache_system.adapters import MemoryCacheAdapter
from app.infrastructure.cache_system.metadata_cache import MetadataCache


def _cache() -> MetadataCache:
    return MetadataCache(adapter=MemoryCacheAdapter(maxsize=100, name="test_metadata"))


def test_detail_cache_is_provider_scoped():
    cache = _cache()
    cache.set_detail("tmdb", "550", {"title": "Fight Club"}, media_type="movie")
    assert cache.get_detail("tmdb", "550", media_type="movie") == {"title": "Fight Club"}
    assert cache.get_detail("douban", "550", media_type="movie") is None
    assert cache.get_detail("tmdb", "550", media_type="tv") is None


def test_detail_cache_scope_and_extra_isolated():
    cache = _cache()
    cache.set_detail("tmdb", "550", {"title": "A"}, media_type="movie", scope="default")
    cache.set_detail("tmdb", "550", {"title": "B"}, media_type="movie", scope="season=2")
    assert (cache.get_detail("tmdb", "550", media_type="movie", scope="default") or {})["title"] == "A"
    assert (cache.get_detail("tmdb", "550", media_type="movie", scope="season=2") or {})["title"] == "B"


def test_clear_provider_only_removes_target_provider():
    cache = _cache()
    cache.set_detail("tmdb", "550", {"title": "A"}, media_type="movie")
    cache.set_detail("douban", "1292000", {"title": "B"}, media_type="movie")
    cache.set_season("tmdb", "1399", 1, {"episodes": []})
    cache.clear_provider("tmdb")
    assert cache.get_detail("tmdb", "550", media_type="movie") is None
    assert cache.get_season("tmdb", "1399", 1) is None
    assert (cache.get_detail("douban", "1292000", media_type="movie") or {})["title"] == "B"


def test_media_cache_uses_generic_keys():
    cache = _cache()
    cache.set_media("Fight Club", {"title": "A"}, year="1999", media_type="movie")
    assert (cache.get_media("Fight Club", year="1999", media_type="movie") or {})["title"] == "A"
