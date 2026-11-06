from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.download_service import DownloadService


def test_downloading_poster_backfills_from_subscription():
    subscribe_repo = MagicMock()
    subscribe_repo.get_movie_subscription_hint.return_value = {"image": "https://img.example/poster.jpg"}
    service = DownloadService(
        downloader=MagicMock(),
        searcher=MagicMock(),
        sites=MagicMock(),
        site_engine=MagicMock(),
        indexer_service=MagicMock(),
        torrent_remover=MagicMock(),
        download_history_repo=MagicMock(),
        subscribe_repo=subscribe_repo,
    )
    task = SimpleNamespace(
        title="ABC-123",
        year="",
        season_episode="",
        poster="",
        anchor_provider="content_id",
        anchor_external_id="ABC-123",
    )

    title, image = service._build_display_info(task)

    assert title.strip() == "ABC-123"
    assert image == "https://img.example/poster.jpg"
    subscribe_repo.get_movie_subscription_hint.assert_called_once_with(
        "content_id", "ABC-123", "ABC-123", identity_id=None
    )
