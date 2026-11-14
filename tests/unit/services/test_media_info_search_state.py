"""媒体搜索卡片订阅状态测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.domain.media_types import ProviderMediaType
from app.services.media_info_service import MediaInfoService


def test_search_media_infos_includes_subscription_state():
    media = SimpleNamespace(
        title="DEMO",
        year="2024",
        type=ProviderMediaType.MOVIE,
        to_dict=lambda: {
            "title": "DEMO",
            "year": "2024",
            "media_type": "movie",
            "tmdb_id": "123",
            "anchor_provider": "tmdb",
            "anchor_external_id": "123",
        },
    )
    svc = MediaInfoService(MagicMock(), MagicMock())
    with (
        patch("app.services.media_info_service.search_media_infos", return_value=[media]),
        patch("app.services.media_info_service.check_media_exists", return_value=("1", "42", "")),
    ):
        result = svc.search_media_infos("demo", "", 1)

    assert result[0]["fav"] == "1"
    assert result[0]["rssid"] == "42"


def test_enrich_search_hits_includes_subscription_state():
    svc = MediaInfoService(MagicMock(), MagicMock())
    hits = [
        {
            "title": "DEMO",
            "year": "2024",
            "media_type": "movie",
            "ref": {"provider": "tmdb", "external_id": "123"},
        }
    ]
    with patch("app.services.media_info_service.check_media_exists", return_value=("1", "42", "")):
        result = svc.enrich_search_hits(hits)
    assert result[0]["fav"] == "1"
    assert result[0]["rssid"] == "42"
