"""set_tmdb_info 类型判定测试：信息缺失不得把 ANIME 误降级为 TV."""

from unittest.mock import MagicMock, patch

from app.domain.mediatypes import MediaType
from app.media import meta_info


def _media(mtype: MediaType):
    m = meta_info(title="Draw This Then Die S01E10 1080p WEB-DL")
    m.type = mtype
    return m


def _patch_categories():
    adapter = MagicMock()
    adapter.get_all.return_value = []
    return patch("app.media.models.CategoryConfigRepositoryAdapter", return_value=adapter)


class TestSetTmdbInfoType:
    def test_missing_genres_preserves_anime(self):
        with _patch_categories():
            m = _media(MediaType.ANIME)
            m.set_tmdb_info({"media_type": MediaType.TV, "id": 287028})
        assert m.type == MediaType.ANIME

    def test_anime_genre_sets_anime(self):
        with _patch_categories():
            m = _media(MediaType.TV)
            m.set_tmdb_info({"media_type": MediaType.TV, "id": 287028, "genre_ids": [16, 35]})
        assert m.type == MediaType.ANIME

    def test_non_anime_genre_sets_tv(self):
        with _patch_categories():
            m = _media(MediaType.ANIME)
            m.set_tmdb_info({"media_type": MediaType.TV, "id": 1, "genre_ids": [35]})
        assert m.type == MediaType.TV

    def test_movie_promoted_to_tv_when_genres_missing(self):
        with _patch_categories():
            m = _media(MediaType.MOVIE)
            m.set_tmdb_info({"media_type": MediaType.TV, "id": 2})
        assert m.type == MediaType.TV
