"""set_provider_data 类型判定测试：信息缺失不得把 ANIME 误降级为 TV."""

from unittest.mock import MagicMock, patch

from app.domain.media_types import ProviderMediaType
from app.media import meta_info


def _media(mtype: ProviderMediaType):
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
            m = _media(ProviderMediaType.ANIME)
            m.set_provider_data({"media_type": ProviderMediaType.SERIES, "id": 287028})
        assert m.type == ProviderMediaType.ANIME

    def test_anime_genre_sets_anime(self):
        with _patch_categories():
            m = _media(ProviderMediaType.SERIES)
            m.set_provider_data({"media_type": ProviderMediaType.SERIES, "id": 287028, "genre_ids": [16, 35]})
        assert m.type == ProviderMediaType.ANIME

    def test_non_anime_genre_sets_tv(self):
        with _patch_categories():
            m = _media(ProviderMediaType.ANIME)
            m.set_provider_data({"media_type": ProviderMediaType.SERIES, "id": 1, "genre_ids": [35]})
        assert m.type == ProviderMediaType.SERIES

    def test_movie_promoted_to_tv_when_genres_missing(self):
        with _patch_categories():
            m = _media(ProviderMediaType.MOVIE)
            m.set_provider_data({"media_type": ProviderMediaType.SERIES, "id": 2})
        assert m.type == ProviderMediaType.SERIES


class TestStringProviderMediaTypeNormalization:
    """TMDB 缓存/批量路径的 media_type 为字符串时也应按 genre 判定动漫."""

    def test_string_tv_with_anime_genre_promotes(self):
        with _patch_categories():
            m = _media(ProviderMediaType.SERIES)
            m.set_provider_data({"media_type": "tv", "id": 9, "genre_ids": [16]})
        assert m.type == ProviderMediaType.ANIME

    def test_string_tv_without_anime_genre_stays_tv(self):
        with _patch_categories():
            m = _media(ProviderMediaType.SERIES)
            m.set_provider_data({"media_type": "tv", "id": 10, "genre_ids": [35]})
        assert m.type == ProviderMediaType.SERIES


def test_set_provider_data_accepts_string_genres():
    from app.media.models import MediaInfo

    m = MediaInfo()
    with _patch_categories():
        m.set_provider_data(
            {
                "media_type": "tv",
                "title": "多元数据动画",
                "genres": ["动画", "剧情"],
            }
        )

    assert m.genres == ["动画", "剧情"]


def test_to_dict_exposes_resolved_type_metadata():
    media = meta_info(title="Demo", mtype=ProviderMediaType.SERIES)
    media.content_profile = "anime"

    data = media.to_dict()

    assert data["type"] == "tv"
    assert data["media_type_name"] == "动漫"
    assert data["media_kind"] == "episodic"
    assert data["media_type_key"] == "anime"
