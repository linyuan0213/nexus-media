"""DiscoveryProvider 与 DiscoveryService 单元测试（无网络）."""

from datetime import date

import pytest

from app.core.exceptions import ValidationError
from app.domain.media_types import MediaKind, ProviderMediaType
from app.media.metadata import (
    DiscoveryFeed,
    DiscoveryItem,
    DiscoveryPage,
    ProviderCapability,
    ProviderDescriptor,
    ProviderRef,
)
from app.media.metadata.providers.bangumi_discovery import BangumiDiscovery
from app.media.metadata.providers.discovery import season_range
from app.media.metadata.providers.douban_discovery import DoubanDiscovery, _douban_discovery_item
from app.media.metadata.providers.tmdb_discovery import TmdbDiscovery, _tmdb_discovery_item
from app.media.metadata.registry import MetadataRegistry
from app.services.discovery_service import DiscoveryService


def test_season_range_supports_anime_and_quarter_names():
    assert season_range("2026-winter") == ("2026-01-01", "2026-03-31")
    assert season_range("2026-spring") == ("2026-04-01", "2026-06-30")
    assert season_range("2026-q3") == ("2026-07-01", "2026-09-30")
    assert season_range("2026-q4") == ("2026-10-01", "2026-12-31")
    assert season_range(None, today=date(2026, 5, 1)) == ("2026-04-01", "2026-06-30")


class _FakeDoubanApi:
    def tv_animation(self, start=0, count=20):
        return {
            "total": 1,
            "subject_collection_items": [
                {
                    "id": "37923549",
                    "title": "动画剧集",
                    "type": "tv",
                    "year": "2026",
                    "photos": ["https://img/still-540x303.webp"],
                    "pic": {
                        "large": "https://img/poster-2x3.webp",
                        "normal": "https://img/poster-small.webp",
                    },
                    "rating": {"value": 8.1},
                    "tags": [],
                }
            ],
        }

    def movie_showing(self, start=0, count=20):
        return {
            "total": 1,
            "subject_collection_items": [
                {
                    "id": "37068446",
                    "title": "生化危机：爆发夜",
                    "type": "movie",
                    "year": "2026",
                    "cover": {"url": "https://img/poster.webp", "width": 4400, "height": 5500},
                    "rating": {"value": 7.3},
                    "tags": [],
                }
            ],
        }


def test_douban_discovery_maps_items():
    provider = DoubanDiscovery(api=_FakeDoubanApi())

    feeds = {feed.key for feed in provider.feeds(None)}
    assert {"movie_showing", "tv_hot", "movie_top250"} <= feeds

    page = provider.items("movie_showing", 1, {}, None)
    item = page.items[0]
    assert item.provider == "douban"
    assert item.title == "生化危机：爆发夜"
    assert item.poster == "https://img/poster.webp"
    assert item.rating == {"douban": 7.3}
    assert item.anchor_ref is not None
    assert item.anchor_ref.external_id == "37068446"
    assert page.has_more is False


def test_discovery_items_do_not_default_unknown_to_movie():
    douban = _douban_discovery_item({"id": "1", "title": "未知条目"})
    assert douban is not None
    assert douban.ref.provider_media_type == ProviderMediaType.UNKNOWN
    assert douban.ref.media_kind == MediaKind.UNKNOWN

    tmdb = _tmdb_discovery_item({"id": 2, "title": "未知条目"})
    assert tmdb is not None
    assert tmdb.ref.provider_media_type == ProviderMediaType.UNKNOWN
    assert tmdb.ref.media_kind == MediaKind.UNKNOWN


def test_douban_discovery_prefers_poster_over_still_photo():
    provider = DoubanDiscovery(api=_FakeDoubanApi())

    page = provider.items("tv_animation", 1, {}, None)

    assert page.items[0].poster == "https://img/poster-2x3.webp"
    assert page.items[0].content_profile == "anime"
    assert page.items[0].ref.provider_media_type == ProviderMediaType.SERIES
    assert page.items[0].ref.media_kind == MediaKind.EPISODIC


class _FakeMediaService:
    def get_tmdb_hot_movies(self, page):
        return [
            {
                "id": 1,
                "title": "电影",
                "type": "movie",
                "media_type": "movie",
                "year": "2026",
                "vote": 8.1,
                "image": "https://img/movie.jpg",
            }
        ]

    def get_tmdb_hot_tvs(self, page):
        return [
            {
                "id": 3,
                "title": "动画剧集",
                "type": "tv",
                "media_type": "tv",
                "year": "2026",
                "vote": 8.2,
                "image": "https://img/anime-tv.jpg",
                "genre_ids": [16],
            }
        ]

    def get_tmdb_trending_all_week(self, page=1):
        return []

    def get_tmdb_discover(self, mtype, params=None, page=1):
        return [
            {
                "id": 2,
                "title": "新剧",
                "type": "tv",
                "media_type": "tv",
                "year": "2026",
                "vote": 7.0,
                "image": "https://img/tv.jpg",
            }
        ]


def test_tmdb_discovery_maps_and_uses_season_facet():
    provider = TmdbDiscovery(_FakeMediaService())

    page = provider.items("seasonal_tv", 1, {"season": "2026-winter"}, None)
    item = page.items[0]
    assert item.provider == "tmdb"
    assert item.title == "新剧"
    assert item.anchor_ref is not None
    assert item.rating == {"tmdb": 7.0}


def test_tmdb_discovery_marks_animated_series_as_anime():
    provider = TmdbDiscovery(_FakeMediaService())

    page = provider.items("popular_tvs", 1, {}, None)

    assert page.items[0].content_profile == "anime"
    assert page.items[0].ref.provider_media_type == ProviderMediaType.SERIES


def test_douban_discovery_marks_animated_items_as_anime_outside_anime_feed():
    item = _douban_discovery_item(
        {"id": "1", "title": "动画剧集", "type": "tv"},
        genres=["动画"],
    )

    assert item is not None
    assert item.content_profile == "anime"


class _FakeBangumi:
    def calendar(self):
        return [
            {
                "weekday": {"cn": "周一"},
                "items": [
                    {
                        "id": 400602,
                        "name": "Tenmaku no Jaadugar",
                        "name_cn": "穹庐下的魔女",
                        "air_date": "2026-01-05",
                        "images": {"large": "https://img/bgm.jpg"},
                        "rating": {"score": 8.2, "rank": 100},
                        "tags": [{"name": "奇幻"}],
                    }
                ],
            }
        ]


def test_bangumi_discovery_filters_by_season():
    provider = BangumiDiscovery(client=_FakeBangumi())

    page = provider.items("seasonal", 1, {"season": "2026-winter"}, None)
    assert [item.title for item in page.items] == ["穹庐下的魔女"]
    assert page.items[0].content_profile == "anime"

    empty = provider.items("seasonal", 1, {"season": "2025-winter"}, None)
    assert empty.items == []


class _FakeDiscoveryProvider:
    descriptor = ProviderDescriptor(
        provider_key="fake",
        display_name="Fake",
        capabilities=frozenset({ProviderCapability.DISCOVERY}),
        visibility="private",
    )

    def feeds(self, ctx):
        return [DiscoveryFeed(key="hot", title="热门", kind="trending")]

    def items(self, feed, page, filters, ctx):
        return DiscoveryPage(items=[], page=page)


def test_discovery_service_filters_private_sources():
    registry = MetadataRegistry()
    registry.register_discovery_provider(_FakeDiscoveryProvider())
    service = DiscoveryService(registry=registry, register_builtins=False)

    assert service.list_sources(allow_private=False) == []
    assert service.list_sources(allow_private=True)[0]["provider"] == "fake"

    with pytest.raises(ValidationError, match="私有来源"):
        service.items("fake", "hot", allow_private=False)

    page = service.items("fake", "hot", allow_private=True)
    assert page.items == []


def test_discovery_service_caches_items():
    class _CountingProvider(_FakeDiscoveryProvider):
        descriptor = ProviderDescriptor(
            provider_key="fake-cache",
            display_name="Fake",
            capabilities=frozenset({ProviderCapability.DISCOVERY}),
        )

        def __init__(self):
            self.calls = 0

        def items(self, feed, page, filters, ctx):
            self.calls += 1
            item = DiscoveryItem(
                provider="fake-cache",
                ref=ProviderRef(provider="fake-cache", external_id="1"),
                title="缓存条目",
            )
            return DiscoveryPage(items=[item], page=page)

    registry = MetadataRegistry()
    provider = _CountingProvider()
    registry.register_discovery_provider(provider)
    service = DiscoveryService(registry=registry, register_builtins=False, cache_ttl_seconds=60)

    service.items("fake-cache", "hot")
    service.items("fake-cache", "hot")

    assert provider.calls == 1
    service.clear_cache()
    service.items("fake-cache", "hot")
    assert provider.calls == 2


def test_discovery_item_country_facets_and_filter():
    from app.media.metadata.providers.discovery import (
        _country_facets,
        _country_filter,
    )

    item = DiscoveryItem(
        provider="bangumi",
        ref=ProviderRef(provider="bangumi", external_id="1"),
        title="日本动画",
        countries=["日本"],
    )
    assert _country_facets([item])[0].value == "日本"
    assert len(_country_filter([item], "日本")) == 1
    assert _country_filter([item], "美国") == []


def test_discovery_feeds_include_country_facet():
    from app.media.metadata.providers.bangumi_discovery import BangumiDiscovery
    from app.media.metadata.providers.douban_discovery import DoubanDiscovery
    from app.media.metadata.providers.tmdb_discovery import TmdbDiscovery

    douban = DoubanDiscovery(api=_FakeDoubanApi())
    tmdb = TmdbDiscovery(None)
    bangumi = BangumiDiscovery(None)
    assert all("country" in feed.facets for feed in douban.feeds(None))
    assert all("country" in feed.facets for feed in tmdb.feeds(None))
    assert all("country" in feed.facets for feed in bangumi.feeds(None))


class _FakeBangumiClient:
    def calendar(self):
        return [
            {
                "weekday": {"id": 1},
                "items": [
                    {
                        "id": 577237,
                        "name": "仙逆剧场版 弑仙之战",
                        "name_cn": "仙逆剧场版 弑仙之战",
                        "air_date": "2026-10-01",
                        "images": {"large": "https://img/cover.webp"},
                        "rating": {"score": 8.0},
                    }
                ],
            }
        ]

    def detail(self, external_id):
        return {"tags": [{"name": "国产"}, {"name": "国漫"}]}


def test_bangumi_uses_subject_tags_for_country():
    provider = BangumiDiscovery(client=_FakeBangumiClient())
    page = provider.items("calendar", 1, {}, None)
    assert page.items[0].countries == ["中国"]
    assert page.facets["country"][0].value == "中国"


def test_bangumi_prefers_majority_japan_tags_over_single_bad_china_tag():
    class _MouseClient(_FakeBangumiClient):
        def detail(self, external_id):
            return {
                "meta_tags": ["日本", "漫画改"],
                "tags": [
                    {"name": "日本", "count": 22},
                    {"name": "国产", "count": 1},
                ],
            }

    provider = BangumiDiscovery(client=_MouseClient())
    page = provider.items("calendar", 1, {}, None)
    assert page.items[0].countries == ["日本"]


def test_country_filter_keeps_all_country_options():
    class _TwoCountryClient:
        def calendar(self):
            return [
                {
                    "weekday": {"id": 1},
                    "items": [
                        {"id": 1, "name": "日本动画", "air_date": "2026-10-01", "images": {}, "rating": {}},
                        {"id": 2, "name": "国产动画", "air_date": "2026-10-02", "images": {}, "rating": {}},
                    ],
                }
            ]

        def detail(self, external_id):
            if str(external_id) == "2":
                return {"tags": [{"name": "国产", "count": 10}]}
            return {"tags": [{"name": "日本", "count": 10}]}

    provider = BangumiDiscovery(client=_TwoCountryClient())
    page = provider.items("calendar", 1, {"country": "日本"}, None)
    assert [item.title for item in page.items] == ["日本动画"]
    country_values = {facet.value for facet in page.facets["country"]}
    assert {"日本", "中国"} <= country_values
