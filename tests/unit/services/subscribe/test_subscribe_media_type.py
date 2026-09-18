"""订阅媒体类型（动漫）保真测试."""

from api.routers.subscription import AddRssMediaRequest, _build_add_kwargs, _build_update_kwargs, _resolve_mtype
from app.domain.media_type_utils import MediaTypeMapper
from app.domain.mediatypes import MediaType
from app.services.subscribe.management.query_service import _resolve_subscribe_type
from app.services.subscribe.management.utils import gen_rss_note
from app.utils import JsonUtils


class TestRouterMediaType:
    def test_resolve_mtype_keeps_anime(self):
        assert _resolve_mtype("anime") == MediaType.ANIME
        assert _resolve_mtype("movie") == MediaType.MOVIE
        assert _resolve_mtype("tv") == MediaType.TV

    def test_resolve_mtype_defaults_tv(self):
        assert _resolve_mtype(None) == MediaType.TV
        assert _resolve_mtype("") == MediaType.TV
        assert _resolve_mtype("whatever") == MediaType.TV

    def test_build_add_kwargs_keeps_anime(self):
        req = AddRssMediaRequest(name="克雷瓦提斯", year="2025", type="anime")
        assert _build_add_kwargs(req)["mtype"] == MediaType.ANIME

    def test_build_update_kwargs_keeps_anime(self):
        req = AddRssMediaRequest(rssid=1, name="克雷瓦提斯", year="2025", type="anime")
        assert _build_update_kwargs(req)["mtype"] == MediaType.ANIME


class TestNoteMediaType:
    def test_gen_rss_note_persists_media_type(self):
        from unittest.mock import MagicMock

        media = MagicMock()
        media.get_poster_image.return_value = "p.jpg"
        media.release_date = "2025-07-01"
        media.vote_average = 8.1
        media.type = MediaType.ANIME
        note = JsonUtils.loads(gen_rss_note(media))
        assert note["media_type"] == "anime"

    def test_resolve_subscribe_type(self):
        assert _resolve_subscribe_type("anime") == "anime"
        assert _resolve_subscribe_type("movie") == "movie"
        assert _resolve_subscribe_type("tv") == "tv"
        assert _resolve_subscribe_type(None) == "tv"
        assert _resolve_subscribe_type("") == "tv"

    def test_anime_maps_to_tv_table(self):
        assert MediaTypeMapper.to_tmdb(MediaType.ANIME) == "tv"
