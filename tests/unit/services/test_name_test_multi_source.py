"""名称识别测试：多数据源匹配与已知来源优先."""

from types import SimpleNamespace
from typing import Any, cast

from app.domain.mediatypes import MediaType
from app.schemas.auth import UserContext
from app.services.media_info_service import MediaInfoService


class _FakeMetadata:
    def list_providers(self, **kwargs):
        return [
            {"provider": "tmdb", "name": "TMDB", "capabilities": ["search"]},
            {"provider": "douban", "name": "豆瓣", "capabilities": ["search"]},
            {"provider": "bangumi", "name": "Bangumi", "capabilities": ["search"]},
        ]

    def search(self, *, query, provider, **kwargs):
        if provider == "tmdb":
            return [
                {
                    "provider": "tmdb",
                    "ref": {"provider": "tmdb", "external_id": "312850"},
                    "title": str(query),
                    "year": "2026",
                    "media_type": "movie",
                    "content_profile": "default",
                    "score": 8.0,
                }
            ]
        if provider == "bangumi" and "乱世" in str(query):
            return [
                {
                    "provider": "bangumi",
                    "ref": {"provider": "bangumi", "external_id": "624085"},
                    "title": "乱世千金",
                    "year": "2026",
                    "media_type": "anime",
                    "content_profile": "anime",
                    "score": 9.0,
                }
            ]
        return []


class _FakeSubscribe:
    def get_subscribe_movies(self, user=None):
        return {}

    def get_subscribe_tvs(self, user=None):
        return {
            "2": {
                "id": 2,
                "name": "乱世千金",
                "metadata_ref": "bangumi:624085",
                "anchor_provider": "bangumi",
            }
        }


def _service() -> MediaInfoService:
    return MediaInfoService(
        media_service=cast(Any, None),
        subscribe=cast(Any, _FakeSubscribe()),
        media_server=cast(Any, None),
        metadata_gateway=cast(Any, _FakeMetadata()),
    )


def _user() -> UserContext:
    return UserContext(
        user_id=1,
        username="admin",
        level=0,
        permissions=["*"],
        role_codes=["superadmin"],
    )


class TestNameTestMultiSource:
    def test_known_subscription_source_is_preferred(self):
        media_info = SimpleNamespace(
            cn_name="乱世千金",
            title="乱世千金",
            type=MediaType.ANIME,
            tmdb_id=None,
        )
        matches, preferred = _service()._identify_matches("乱世千金 第3集", media_info, _user())
        assert preferred == {
            "provider": "bangumi",
            "label": "Bangumi",
            "reason": "命中已有订阅来源",
        }
        assert matches[0]["provider"] == "bangumi"
        assert matches[0]["preferred"] is True
        assert {match["provider"] for match in matches} == {"bangumi", "tmdb"}

    def test_no_known_source_still_returns_multi_source_matches(self):
        media_info = SimpleNamespace(
            cn_name="Spider-Man",
            title="Spider-Man",
            type=MediaType.MOVIE,
            tmdb_id=None,
        )
        service = _service()
        matches, preferred = service._identify_matches("Spider-Man", media_info, _user())
        assert preferred is None
        assert {match["provider"] for match in matches} == {"tmdb"}
