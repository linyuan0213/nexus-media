"""订阅媒体类型（动漫）保真测试."""

from api.routers.subscription import (
    AddRssMediaRequest,
    _build_add_kwargs,
    _build_update_kwargs,
    _resolve_mtype,
    _resolve_type_and_profile,
)
from app.domain.media_type_utils import ProviderMediaTypeMapper
from app.domain.media_types import MediaKind, ProviderMediaType
from app.media.metadata.providers.genres import (
    classify_media_type,
    classify_provider_media_type,
    is_anime_genre,
)
from app.media.models import MediaInfo
from app.services.subscribe.management.query_service import _resolve_subscribe_type, _source_label
from app.services.subscribe.management.utils import gen_rss_note
from app.utils import JsonUtils


class TestRouterProviderMediaType:
    def test_resolve_mtype_keeps_anime(self):
        assert _resolve_mtype("anime") == ProviderMediaType.ANIME
        assert _resolve_mtype("movie") == ProviderMediaType.MOVIE
        assert _resolve_mtype("tv") == ProviderMediaType.SERIES

    def test_resolve_mtype_defaults_tv(self):
        assert _resolve_mtype(None) == ProviderMediaType.SERIES
        assert _resolve_mtype("") == ProviderMediaType.SERIES
        assert _resolve_mtype("whatever") == ProviderMediaType.SERIES

    def test_build_add_kwargs_keeps_anime(self):
        req = AddRssMediaRequest(name="克雷瓦提斯", year="2025", type="anime")
        assert _build_add_kwargs(req)["mtype"] == ProviderMediaType.ANIME

    def test_build_update_kwargs_keeps_anime(self):
        req = AddRssMediaRequest(rssid=1, name="克雷瓦提斯", year="2025", type="anime")
        assert _build_update_kwargs(req)["mtype"] == ProviderMediaType.ANIME

    def test_non_default_profile_uses_movie_carrier(self):
        mtype, profile = _resolve_type_and_profile("legacy-plugin-type", "demo")
        assert mtype == ProviderMediaType.MOVIE
        assert profile == "demo"

    def test_plugin_profile_defaults_to_movie_carrier(self):
        mtype, profile = _resolve_type_and_profile("demo", "demo")
        assert mtype == ProviderMediaType.MOVIE
        assert profile == "demo"

    def test_build_kwargs_carry_provider_and_profile(self):
        req = AddRssMediaRequest(
            name="SSIS-001",
            type="legacy-plugin-type",
            content_profile="demo",
            provider="demo_meta",
            metadata_ref="demo_meta:AbCdEf",
            mediaid="content_id:SSIS-001",
        )
        add = _build_add_kwargs(req)
        assert add["mtype"] == ProviderMediaType.MOVIE
        assert add["content_profile"] == "demo"
        assert add["provider"] == "demo_meta"
        assert add["metadata_ref"] == "demo_meta:AbCdEf"
        update = _build_update_kwargs(AddRssMediaRequest(rssid=1, **req.model_dump(exclude={"rssid"})))
        assert update["content_profile"] == "demo"
        assert update["provider"] == "demo_meta"


class TestGenericAnimeClassification:
    def test_tmdb_and_douban_genres(self):
        assert is_anime_genre([{"id": 16, "name": "Animation"}])
        assert is_anime_genre(["动画", "动作"])
        assert not is_anime_genre(["剧情"])
        assert classify_media_type(ProviderMediaType.SERIES, ["动画"]) == (ProviderMediaType.ANIME, "anime")
        assert classify_media_type(ProviderMediaType.SERIES, ["剧情"]) == (ProviderMediaType.SERIES, "default")
        # 电影保持电影，不因为动画题材被塞进电视剧表
        assert classify_media_type(ProviderMediaType.MOVIE, ["动画"]) == (ProviderMediaType.MOVIE, "default")

    def test_provider_classification_uses_kind_and_keeps_anime(self):
        assert classify_provider_media_type(ProviderMediaType.SERIES, ["动画"]) == (
            ProviderMediaType.ANIME,
            "anime",
        )
        assert classify_provider_media_type(ProviderMediaType.SERIES, ["剧情"]) == (
            ProviderMediaType.SERIES,
            "default",
        )
        assert classify_provider_media_type(ProviderMediaType.MOVIE, ["动画"]) == (
            ProviderMediaType.MOVIE,
            "default",
        )
        assert ProviderMediaType.SERIES.kind == MediaKind.EPISODIC
        assert ProviderMediaType.ANIME.kind == MediaKind.EPISODIC

    def test_note_genres_resolve_anime_without_tmdb(self):
        assert _resolve_subscribe_type("tv", None, ["动画"]) == ProviderMediaType.ANIME.value
        assert _resolve_subscribe_type("tv", None, ["剧情"]) == ProviderMediaType.SERIES.value

    def test_gen_rss_note_persists_genres(self):
        media = MediaInfo(type=ProviderMediaType.ANIME, title="测试番剧", genres=["动画"])
        note = JsonUtils.loads(gen_rss_note(media))
        assert note["media_type"] == "anime"
        assert note["genres"] == ["动画"]


class TestSourceLabel:
    def test_content_id_anchor_falls_back_to_metadata_provider(self):
        assert _source_label("content_id", None, "demo_meta:AbCdEf").lower() == "demo_meta"

    def test_missing_provider_uses_plugin_label(self):
        assert _source_label("content_id") == "插件"


class TestNoteProviderMediaType:
    def test_gen_rss_note_persists_media_type(self):
        from unittest.mock import MagicMock

        media = MagicMock()
        media.get_poster_image.return_value = "p.jpg"
        media.release_date = "2025-07-01"
        media.vote_average = 8.1
        media.type = ProviderMediaType.ANIME
        note = JsonUtils.loads(gen_rss_note(media))
        assert note["media_type"] == "anime"

    def test_resolve_subscribe_type(self):
        assert _resolve_subscribe_type("anime") == "anime"
        assert _resolve_subscribe_type("movie") == "movie"
        assert _resolve_subscribe_type("tv") == "tv"
        assert _resolve_subscribe_type(None) == "tv"
        assert _resolve_subscribe_type("") == "tv"
        # 有 TMDB ID 但缺少网关时不能静默降级成 TV
        assert _resolve_subscribe_type(None, 258348) == "unknown"

    def test_anime_maps_to_tv_table(self):
        assert ProviderMediaTypeMapper.to_tmdb(ProviderMediaType.ANIME) == "tv"


def test_media_type_from_chinese_display_name():
    from app.domain.media_types import ProviderMediaType

    assert ProviderMediaType.from_value("电影") == ProviderMediaType.MOVIE
    assert ProviderMediaType.from_value("电视剧") == ProviderMediaType.SERIES
    assert ProviderMediaType.from_value("动漫") == ProviderMediaType.ANIME
