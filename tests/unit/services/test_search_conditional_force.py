"""刷新重下：已入库/活动任务不得重复，未入库且无活动任务才允许."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.search_service import SearchResultProcessor
from app.services.subscription_download_guard import SubscriptionDownloadGuard


def _processor(rows):
    repo = MagicMock()
    repo.is_completed_by_identity.return_value = True
    repo.get_by_identity.return_value = rows
    return SearchResultProcessor(
        downloader=MagicMock(),
        download_repo=repo,
        search_repo=MagicMock(),
        message=MagicMock(),
    )


def _media():
    media = MagicMock()
    media.tmdb_id = None
    media.title = "ACHJ-097"
    media.identity_id = "id"
    media.get_media_ref.return_value = MagicMock(provider="demo_meta", external_id="ACHJ-097")
    media.get_season_episode_string.return_value = ""
    return media


def test_force_allows_when_only_completed_history():
    media = _media()
    processor = _processor([SimpleNamespace(state="completed")])
    assert processor.filter_downloaded([media], force=True) == [media]


def test_force_blocks_when_active_download_exists():
    media = _media()
    processor = _processor([SimpleNamespace(state="downloading")])
    assert processor.filter_downloaded([media], force=True) == []


def test_active_guard_queries_tmdb_and_series_identity():
    """普通 TMDB 订阅没有 anchor 时也要查在途下载，不能只按 identity/anchor 判空."""
    repo = MagicMock()
    repo.has_active_download_for_media.return_value = False
    media = SimpleNamespace(
        identity_id=None,
        anchor_provider=None,
        anchor_external_id=None,
        tmdb_id="123",
        series_key="series:demo",
        title="Demo show",
        get_season_episode_string=lambda: "S01 E01",
    )

    SubscriptionDownloadGuard(repo).filter_candidates([media])

    repo.has_active_download_for_media.assert_called_once_with(
        identity_id=None,
        anchor_provider=None,
        anchor_external_id=None,
        tmdb_id="123",
        series_key="series:demo",
        season_episode="S01 E01",
    )
