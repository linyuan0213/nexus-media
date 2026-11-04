"""刷新重下：已入库/活动任务不得重复，未入库且无活动任务才允许."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.search_service import SearchResultProcessor


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
