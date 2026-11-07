"""订阅实体映射测试：新身份字段必须能读出."""

from types import SimpleNamespace

from app.domain.entities.rss import SubscribeHistoryEntity, SubscribeMovieEntity, SubscribeTvEntity
from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo


def _base(**extra):
    data = {
        "ID": 1,
        "NAME": "测试",
        "YEAR": "2024",
        "KEYWORD": "",
        "TMDBID": "DB:123",
        "IMAGE": "",
        "RSS_SITES": "[]",
        "SEARCH_SITES": "[]",
        "OVER_EDITION": 0,
        "FILTER_ORDER": 0,
        "FILTER_RESTYPE": "",
        "FILTER_PIX": "",
        "FILTER_RULE": 0,
        "FILTER_TEAM": "",
        "FILTER_INCLUDE": "",
        "FILTER_EXCLUDE": "",
        "FILTER_FREE": 0,
        "SAVE_PATH": "",
        "DOWNLOAD_SETTING": -1,
        "FUZZY_MATCH": 0,
        "STATE": "D",
        "DESC": "",
        "NOTE": "",
        "ADD_DATE": "2026-01-01",
        "USER_ID": 1,
        "IDENTITY_ID": "01J00000000000000000000000",
        "ANCHOR_PROVIDER": "douban",
        "ANCHOR_EXTERNAL_ID": "123",
        "CONTENT_PROFILE": "default",
        "METADATA_POLICY": "douban_primary",
        "NAMING_PROFILE": None,
    }
    data.update(extra)
    return SimpleNamespace(**data)


def test_movie_entity_maps_identity_fields():
    entity = SubscribeMovieEntity.from_orm(_base())

    assert entity is not None
    assert entity.identity_id == "01J00000000000000000000000"
    assert entity.anchor_provider == "douban"
    assert entity.anchor_external_id == "123"
    assert entity.metadata_policy == "douban_primary"
    assert entity.to_dict()["anchor_provider"] == "douban"


def test_tv_entity_maps_identity_fields():
    entity = SubscribeTvEntity.from_orm(_base(SEASON="1", TOTAL_EP=9, CURRENT_EP=1, TOTAL=9, LACK=9))

    assert entity is not None
    assert entity.identity_id == "01J00000000000000000000000"
    assert entity.content_profile == "default"
    assert entity.to_dict()["identity_id"] == "01J00000000000000000000000"


def test_web_utils_douban_fallback_does_not_supplement_tmdb():
    from unittest.mock import MagicMock

    from app.domain.media_types import ProviderMediaType
    from app.services.web.utils import WebUtils

    media_service = MagicMock()
    media_service.get_media_info.return_value = None
    gateway = MagicMock()
    gateway.lookup.return_value = {
        "title": "最后生还者 第一季",
        "original_title": "The Last of Us Season 1",
        "year": "2023",
        "media_type": "tv",
        "content_profile": "default",
        "images": {"poster": [{"url": "https://img/poster.jpg"}]},
        "seasons": [{"season_number": 1, "episode_count": 9}],
    }
    media_service.get_media_info.return_value = None
    utils = WebUtils(metadata_gateway=gateway)

    info = utils.get_mediainfo_from_id(ProviderMediaType.SERIES, "DB:25848328")

    assert info is not None
    assert info.tmdb_id == ""
    assert info.douban_id == "25848328"
    assert info.anchor_provider == "douban"
    assert info.anchor_external_id == "25848328"
    assert info.total_episodes == 9
    assert info.begin_season == 1
    media_service.get_tmdb_info.assert_not_called()
    media_service.get_media_info.assert_not_called()


def test_detail_links_follow_anchor_and_keep_tmdb_supplement():
    info = MediaInfo(
        type=ProviderMediaType.SERIES,
        title="权力的游戏",
        tmdb_id=1399,
        douban_id="26584183",
        anchor_provider="douban",
        anchor_external_id="26584183",
    )
    assert info.get_detail_url() == "https://movie.douban.com/subject/26584183"
    links = {item["provider"]: item["url"] for item in info.get_detail_links()}
    assert links["douban"] == "https://movie.douban.com/subject/26584183"
    assert links["tmdb"] == "https://www.themoviedb.org/tv/1399"
    assert info.get_detail_url("tmdb") == "https://www.themoviedb.org/tv/1399"


def test_media_info_exposes_typed_ref():
    info = MediaInfo(
        type=ProviderMediaType.SERIES,
        tmdb_id="1399",
        anchor_provider="douban",
        anchor_external_id="26584183",
    )
    ref = info.get_media_ref()
    assert ref is not None
    assert (ref.provider, ref.external_id) == ("douban", "26584183")


def test_history_entity_maps_identity_fields():
    row = SimpleNamespace(
        ID=1,
        TYPE="movie",
        RSSID="rss-1",
        NAME="历史",
        YEAR="2024",
        TMDBID="DB:123",
        SEASON="",
        IMAGE="",
        DESC="",
        TOTAL=0,
        START=0,
        FINISH_TIME="2026-01-01 00:00:00",
        NOTE="",
        USER_ID=1,
        IDENTITY_ID="01J00000000000000000000000",
        ANCHOR_PROVIDER="douban",
        ANCHOR_EXTERNAL_ID="123",
        CONTENT_PROFILE="default",
        METADATA_POLICY="douban_primary",
        NAMING_PROFILE=None,
    )
    entity = SubscribeHistoryEntity.from_orm(row)

    assert entity is not None
    assert entity.to_dict()["anchor_provider"] == "douban"
    assert entity.to_dict()["metadata_policy"] == "douban_primary"


class _SeriesRow:
    SERIES_KEY = "series:demo"

    def __getattr__(self, name):
        return None


def test_subscription_entities_keep_series_key():
    from app.domain.entities.rss import SubscribeMovieEntity, SubscribeTvEntity

    tv = SubscribeTvEntity.from_orm(_SeriesRow())
    movie = SubscribeMovieEntity.from_orm(_SeriesRow())
    assert tv is not None and tv.series_key == "series:demo"
    assert movie is not None and movie.series_key == "series:demo"


def test_media_ref_and_identity_key_legacy_prefixes():
    from app.domain.media_ref import identity_keys_match, media_identity_key
    from app.media.models import MediaInfo

    info = MediaInfo(title="Legacy", tmdb_id="DB:12345")
    ref = info.get_media_ref()
    assert ref is not None
    assert ref.provider == "douban"
    assert ref.external_id == "12345"
    assert identity_keys_match(media_identity_key(info), "DB:12345")
    assert identity_keys_match(media_identity_key(info), "douban:12345")
    assert identity_keys_match("123", "TMDB:123")


def test_media_detail_links_follow_anchor():
    from app.media.models import MediaInfo

    info = MediaInfo(
        title="Anchored",
        tmdb_id="",
        anchor_provider="bangumi",
        anchor_external_id="456",
    )
    links = {item["provider"]: item["url"] for item in info.get_detail_links()}
    assert links["bangumi"].endswith("/456")
