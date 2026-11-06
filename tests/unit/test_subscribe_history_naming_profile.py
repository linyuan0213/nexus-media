from unittest.mock import MagicMock

from app.services.subscribe_repo_adapter import SubscribeHistoryRepositoryAdapter


def test_history_upsert_accepts_naming_profile():
    repo = MagicMock()
    adapter = SubscribeHistoryRepositoryAdapter(repo)

    adapter.upsert(
        rssid=1,
        rtype="movie",
        name="ABC-123",
        year="2026",
        tmdbid="content_id:ABC-123",
        image="poster.jpg",
        desc="desc",
        naming_profile="demo.default",
    )

    assert repo.upsert_rss_history.call_args.kwargs["naming_profile"] == "demo.default"


def test_history_insert_accepts_naming_profile():
    repo = MagicMock()
    adapter = SubscribeHistoryRepositoryAdapter(repo)

    adapter.insert(
        rssid=1,
        rtype="movie",
        name="ABC-123",
        year="2026",
        tmdbid="content_id:ABC-123",
        image="poster.jpg",
        desc="desc",
        naming_profile="demo.default",
    )

    assert repo.insert_rss_history.call_args.kwargs["naming_profile"] == "demo.default"
