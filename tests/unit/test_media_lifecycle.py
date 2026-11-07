"""媒体生命周期读模型与状态映射测试."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.db.engine import get_engine
from app.db.models import Base
from app.db.models.lifecycle import MediaLifecycle
from app.db.models.subscribe import SubscribeTvs
from app.db.repositories import lifecycle_repository as lifecycle_repo_module
from app.db.repositories.lifecycle_repository import LifecycleRepository
from app.domain.lifecycle import (
    LifecycleStage,
    LifecycleStatus,
    map_download_state,
    map_subscribe_state,
    map_task_status,
    map_torrent_status,
)
from app.services.lifecycle_service import LifecycleProjector, _parse_season_episodes


@pytest.fixture(autouse=True)
def _clean_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def test_status_mapping():
    assert map_task_status("queued") is LifecycleStatus.QUEUED
    assert map_task_status("succeeded") is LifecycleStatus.SUCCEEDED
    assert map_torrent_status("Pending") == (LifecycleStage.DOWNLOAD_QUEUED, LifecycleStatus.QUEUED)
    assert map_torrent_status("Downloading") == (LifecycleStage.DOWNLOADING, LifecycleStatus.RUNNING)
    assert map_download_state("completed") == (LifecycleStage.DOWNLOADED, LifecycleStatus.SUCCEEDED)
    assert map_subscribe_state("R") == (LifecycleStage.SUBSCRIBED, LifecycleStatus.RUNNING)


def test_projector_is_idempotent_and_keeps_latest_state():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    assert projector.record(
        identity_id="identity-1",
        stage=LifecycleStage.DOWNLOADING,
        status=LifecycleStatus.RUNNING,
        event_type="download.started",
        title="Demo",
        trace_id="trace-1",
        progress=10,
        event_key="event-1",
        occurred_at=now,
    )
    assert not projector.record(
        identity_id="identity-1",
        stage=LifecycleStage.DOWNLOADING,
        status=LifecycleStatus.RUNNING,
        event_type="download.started",
        event_key="event-1",
        occurred_at=now,
    )
    current = repo.get_current("identity-1")
    assert current is not None
    assert current.STAGE == LifecycleStage.DOWNLOADING.value
    assert current.PROGRESS == 10
    assert current.TITLE == "Demo"

    # 旧事件不能回退当前状态，但会保留在时间线里
    assert projector.record(
        identity_id="identity-1",
        stage=LifecycleStage.DOWNLOAD_QUEUED,
        status=LifecycleStatus.QUEUED,
        event_type="download.queued",
        event_key="event-0",
        occurred_at=now - timedelta(minutes=1),
    )
    current = repo.get_current("identity-1")
    assert current is not None
    assert current.STAGE == LifecycleStage.DOWNLOADING.value
    assert len(repo.list_events("identity-1")) == 2

    # 新阶段更新快照
    assert projector.record(
        identity_id="identity-1",
        stage=LifecycleStage.DOWNLOADED,
        status=LifecycleStatus.SUCCEEDED,
        event_type="download.completed",
        event_key="event-2",
        occurred_at=now + timedelta(minutes=2),
    )
    current = repo.get_current("identity-1")
    assert current is not None
    assert current.STAGE == LifecycleStage.DOWNLOADED.value
    assert current.STATUS == LifecycleStatus.SUCCEEDED.value
    assert current.STAGE_STARTED_AT == now + timedelta(minutes=2)
    assert current.PROGRESS == 100


def test_list_and_owner_filter():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    projector.record(
        identity_id="identity-1",
        stage=LifecycleStage.DOWNLOADING,
        status=LifecycleStatus.RUNNING,
        event_type="download.started",
        title="Owner A",
        user_id=1,
        event_key="a",
    )
    projector.record(
        identity_id="identity-2",
        stage=LifecycleStage.DOWNLOADING,
        status=LifecycleStatus.RUNNING,
        event_type="download.started",
        title="Owner B",
        user_id=2,
        event_key="b",
    )
    rows, total = repo.list_current(keyword="Owner", user=None)
    assert total == 2
    assert len(rows) == 2
    summary = repo.stats_current()
    assert summary["total"] == 2
    assert summary["by_status"]["running"] == 2


def test_reconciler_backfills_download_and_transfer_history():
    from sqlalchemy.orm import sessionmaker

    from app.db.engine import get_engine
    from app.db.models.download import DOWNLOADHISTORY
    from app.db.models.transfer import TRANSFERHISTORY
    from app.services.lifecycle_service import LifecycleReconciler

    session = sessionmaker(bind=get_engine())()
    session.add(
        DOWNLOADHISTORY(
            TITLE="Reconcile Demo",
            YEAR="2024",
            TYPE="MOV",
            TMDBID="",
            SE="",
            VOTE="",
            POSTER="",
            OVERVIEW="",
            TORRENT="",
            ENCLOSURE="",
            SITE="",
            DESC="",
            DOWNLOADER="4",
            DOWNLOAD_ID="reconcile-1",
            SAVE_PATH="/tmp",
            STATE="completed",
            DATE="2026-11-02 10:00:00",
            IDENTITY_ID="reconcile-identity",
            ANCHOR_PROVIDER="tmdb",
            ANCHOR_EXTERNAL_ID="550",
            CONTENT_PROFILE="default",
        )
    )
    session.add(
        TRANSFERHISTORY(
            MODE="copy",
            TYPE="MOV",
            CATEGORY="外语电影",
            TMDBID=550,
            TITLE="Reconcile Demo",
            YEAR="2024",
            SEASON_EPISODE="",
            SOURCE="download",
            SOURCE_PATH="/tmp/source",
            SOURCE_FILENAME="source.mkv",
            DEST="/tmp/dest",
            DEST_PATH="/tmp/dest",
            DEST_FILENAME="dest.mkv",
            DATE="2026-11-02 11:00:00",
            IDENTITY_ID=None,
            ANCHOR_PROVIDER="dmm",
            ANCHOR_EXTERNAL_ID="550",
            CONTENT_PROFILE="default",
            SOURCE_STATE="present",
            DEST_STATE="present",
        )
    )
    session.commit()
    session.close()

    result = LifecycleReconciler().reconcile_recent(limit=10)

    assert result["imported"] == 2
    current = LifecycleRepository().get_current("reconcile-identity")
    assert current is not None
    assert current.STAGE == LifecycleStage.TRANSFERRED.value
    assert current.STATUS == LifecycleStatus.SUCCEEDED.value
    assert current.TITLE == "Reconcile Demo"
    assert LifecycleRepository().get_current("transfer-identity") is None


def test_grouped_list_collapses_episodes_by_identity():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    projector.record(
        identity_id="series-1",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        media_type="tv",
        season=1,
        episode=1,
        title="Series",
        event_key="ep1",
    )
    projector.record(
        identity_id="series-1",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        media_type="tv",
        season=1,
        episode=2,
        title="Series",
        event_key="ep2",
    )
    rows, total = repo.list_grouped(page=1, pagenum=20)
    assert total == 1
    assert len(rows) == 1
    assert rows[0]["EPISODE_COUNT"] == 2
    assert rows[0]["COMPLETED_EPISODES"] == 2
    assert rows[0]["STAGE"] == LifecycleStage.IN_LIBRARY.value


def test_grouped_incomplete_subscription_keeps_library_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    for episode in range(1, 5):
        projector.record(
            identity_id="identity-tv",
            stage=LifecycleStage.IN_LIBRARY,
            status=LifecycleStatus.SUCCEEDED,
            event_type="library.present",
            title="Demo TV",
            media_type="tv",
            season=1,
            episode=episode,
            event_key=f"library-{episode}",
            occurred_at=now,
        )
    with repo.session() as db:
        db.add(
            SubscribeTvs(
                NAME="Demo TV",
                SEASON="S01",
                TOTAL_EP=12,
                CURRENT_EP=6,
                STATE="D",
                IDENTITY_ID="identity-tv",
            )
        )
        db.commit()

    rows, total = repo.list_grouped(pagenum=100)
    assert total == 1
    item = rows[0]
    assert item["EPISODE_COUNT"] == 12
    assert item["COMPLETED_EPISODES"] == 4
    assert item["SUBSCRIBED_EPISODES"] == 5
    assert item["PROGRESS"] == 33
    assert item["STAGE"] == LifecycleStage.IN_LIBRARY.value
    assert item["STATUS"] == LifecycleStatus.QUEUED.value


def test_snapshot_does_not_regress_to_earlier_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    assert projector.record(
        identity_id="identity-monotonic",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        event_key="library-1",
        occurred_at=now,
    )
    assert projector.record(
        identity_id="identity-monotonic",
        stage=LifecycleStage.DOWNLOADED,
        status=LifecycleStatus.SUCCEEDED,
        event_type="download.completed",
        event_key="download-late",
        occurred_at=now + timedelta(hours=1),
    )
    current = repo.get_current("identity-monotonic")
    assert current is not None
    assert current.STAGE == LifecycleStage.IN_LIBRARY.value


def test_existing_event_repairs_regressed_snapshot():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    projector.record(
        identity_id="identity-repair",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        event_key="library-repair",
        occurred_at=now,
    )
    with repo.session() as db:
        current = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == "identity-repair").one()
        current.STAGE = LifecycleStage.DOWNLOADED.value
        current.LAST_EVENT_AT = now + timedelta(hours=1)
        db.commit()
    projector.record(
        identity_id="identity-repair",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        event_key="library-repair",
        occurred_at=now,
    )
    current = repo.get_current("identity-repair")
    assert current is not None
    assert current.STAGE == LifecycleStage.IN_LIBRARY.value


def test_duplicate_background_event_does_not_restart_library_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    queued_at = datetime(2026, 11, 2, 9, 0, 0)
    library_at = queued_at + timedelta(hours=1)
    projector.record(
        identity_id="identity-duplicate",
        stage=LifecycleStage.TRANSFER_QUEUED,
        status=LifecycleStatus.QUEUED,
        event_type="transfer.queued",
        event_key="duplicate-transfer-queued",
        occurred_at=queued_at,
    )
    projector.record(
        identity_id="identity-duplicate",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        event_key="duplicate-library",
        occurred_at=library_at,
    )
    # 重启后旧事件被重新投递，但 EVENT_KEY 相同，不能按新时间开启新一轮流转。
    projector.record(
        identity_id="identity-duplicate",
        stage=LifecycleStage.TRANSFER_QUEUED,
        status=LifecycleStatus.QUEUED,
        event_type="transfer.queued",
        event_key="duplicate-transfer-queued",
        occurred_at=library_at + timedelta(hours=2),
    )
    current = repo.get_current("identity-duplicate")
    assert current is not None
    assert current.STAGE == LifecycleStage.IN_LIBRARY.value
    assert current.STATUS == LifecycleStatus.SUCCEEDED.value
    assert current.LAST_EVENT_AT == library_at


def test_grouped_reads_active_subscriptions_inside_open_session(monkeypatch):
    seen: dict[str, bool] = {}
    original = lifecycle_repo_module._active_subscription_items

    def spy(db, user, existing):
        seen["in_transaction"] = db.in_transaction()
        return original(db, user, existing)

    monkeypatch.setattr(lifecycle_repo_module, "_active_subscription_items", spy)
    LifecycleRepository().list_grouped(pagenum=10)
    assert seen["in_transaction"] is True


def test_grouped_cancelled_subscription_projects_cancelled_status():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    projector.record(
        identity_id="identity-cancelled",
        stage=LifecycleStage.SUBSCRIBED,
        status=LifecycleStatus.RUNNING,
        event_type="search.started",
        title="Cancelled Demo",
        media_type="tv",
        season=2,
        event_key="search-cancelled",
    )

    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["STAGE"] == LifecycleStage.SUBSCRIBED.value
    assert rows[0]["STATUS"] == LifecycleStatus.CANCELLED.value

    with repo.session() as db:
        db.add(
            SubscribeTvs(
                NAME="Cancelled Demo",
                SEASON="S02",
                TOTAL_EP=12,
                CURRENT_EP=0,
                STATE="S",
                IDENTITY_ID="identity-cancelled",
            )
        )
        db.commit()

    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["STATUS"] == LifecycleStatus.RUNNING.value


def test_grouped_cancel_event_overrides_downloaded_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    projector.record(
        identity_id="identity-cancel-downloaded",
        stage=LifecycleStage.DOWNLOADED,
        status=LifecycleStatus.SUCCEEDED,
        event_type="download.completed",
        title="Downloaded Cancel Demo",
        media_type="movie",
        event_key="downloaded-cancel",
    )
    projector.record_subscription_outcome(
        identity_id="identity-cancel-downloaded",
        status=LifecycleStatus.CANCELLED,
        event_type="subscribe.cancelled",
        media_type="movie",
        title="Downloaded Cancel Demo",
        event_key="cancel-downloaded",
    )

    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["STAGE"] == LifecycleStage.DOWNLOADED.value
    assert rows[0]["STATUS"] == LifecycleStatus.CANCELLED.value


def test_grouped_stage_uses_furthest_episode():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    for episode, stage in ((1, LifecycleStage.DOWNLOADED), (2, LifecycleStage.IN_LIBRARY)):
        projector.record(
            identity_id="identity-stage",
            stage=stage,
            status=LifecycleStatus.SUCCEEDED,
            event_type="episode",
            media_type="tv",
            season=1,
            episode=episode,
            event_key=f"episode-{episode}",
            occurred_at=now,
        )
    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["STAGE"] == LifecycleStage.IN_LIBRARY.value


def test_grouped_ignores_series_level_placeholder_when_episodes_exist():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    projector.record(
        identity_id="identity-placeholder",
        stage=LifecycleStage.DOWNLOADED,
        status=LifecycleStatus.SUCCEEDED,
        event_type="season.downloaded",
        media_type="tv",
        event_key="season-level",
        occurred_at=now,
    )
    projector.record(
        identity_id="identity-placeholder",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="episode.library",
        media_type="tv",
        season=1,
        episode=1,
        event_key="episode-1",
        occurred_at=now,
    )
    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["EPISODE_COUNT"] == 1
    assert rows[0]["COMPLETED_EPISODES"] == 1
    assert rows[0]["STAGE"] == LifecycleStage.IN_LIBRARY.value


def test_active_subscription_with_library_episodes_keeps_library_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    for episode in (1, 2):
        projector.record(
            identity_id="identity-active",
            stage=LifecycleStage.IN_LIBRARY,
            status=LifecycleStatus.SUCCEEDED,
            event_type="library.present",
            media_type="tv",
            season=1,
            episode=episode,
            event_key=f"library-active-{episode}",
            occurred_at=now,
        )
    with repo.session() as db:
        db.add(
            SubscribeTvs(
                NAME="Active TV",
                SEASON="S01",
                TOTAL_EP=2,
                CURRENT_EP=2,
                STATE="R",
                IDENTITY_ID="identity-active",
            )
        )
        db.commit()
    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["STAGE"] == LifecycleStage.IN_LIBRARY.value
    assert rows[0]["STATUS"] == LifecycleStatus.RUNNING.value


def test_active_subscription_with_scraped_episode_keeps_scraped_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    projector.record(
        identity_id="identity-scraped",
        stage=LifecycleStage.SCRAPED,
        status=LifecycleStatus.SUCCEEDED,
        event_type="scrape.completed",
        media_type="tv",
        season=1,
        episode=1,
        event_key="scrape-active-1",
        occurred_at=now,
    )
    with repo.session() as db:
        db.add(
            SubscribeTvs(
                NAME="Scraped TV",
                SEASON="S01",
                TOTAL_EP=2,
                CURRENT_EP=2,
                STATE="R",
                IDENTITY_ID="identity-scraped",
            )
        )
        db.commit()
    rows, total = repo.list_grouped(pagenum=10)
    assert total == 1
    assert rows[0]["STAGE"] == LifecycleStage.SCRAPED.value
    assert rows[0]["STATUS"] == LifecycleStatus.RUNNING.value


def test_parse_season_episodes_expands_range():
    assert _parse_season_episodes("S01 E01-E03") == [(1, 1), (1, 2), (1, 3)]
    assert _parse_season_episodes("S01E06-E08") == [(1, 6), (1, 7), (1, 8)]
    assert _parse_season_episodes("S01 E04") == [(1, 4)]
    assert _parse_season_episodes("") == [(0, 0)]


def test_manual_identify_updates_metadata():
    from app.services.lifecycle_action_service import LifecycleActionService

    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    projector.record(
        identity_id="identity-identify",
        stage=LifecycleStage.IDENTIFIED,
        status=LifecycleStatus.FAILED,
        event_type="identify.failed",
        title="Old",
        event_key="identify-failed",
        occurred_at=now,
    )
    LifecycleActionService(repo, projector).identify(
        "identity-identify",
        provider="tmdb",
        external_id="123",
        title="New title",
        year="2024",
    )
    current = repo.get_current("identity-identify")
    assert current is not None
    assert current.TITLE == "New title"
    assert current.YEAR == "2024"
    assert current.SOURCE_PROVIDER == "tmdb"


def test_pause_download_calls_downloader():
    from app.domain.lifecycle import LifecycleStage
    from app.services.lifecycle_action_service import LifecycleActionService

    repo = Mock()
    repo.latest_download_task.return_value = ("qbittorrent", "hash-1")
    repo.get_current.return_value = SimpleNamespace(
        STAGE=LifecycleStage.DOWNLOADING.value,
        STATUS="running",
        MEDIA_TYPE="movie",
        SEASON=0,
        EPISODE=0,
        RUN_ID="run-1",
        TRACE_ID="trace-1",
        TITLE="Demo",
        YEAR="2024",
        POSTER=None,
        SOURCE_PROVIDER="tmdb",
        CONTENT_PROFILE="default",
        USER_ID=1,
    )
    projector = Mock()
    downloader = Mock()
    LifecycleActionService(repo, projector, downloader).pause("identity-pause")
    downloader.stop_torrents.assert_called_once_with("qbittorrent", ["hash-1"])
    projector.record.assert_called_once()


def test_timeline_is_chronological():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    projector.record(
        identity_id="identity-timeline",
        stage=LifecycleStage.TRANSFERRED,
        status=LifecycleStatus.SUCCEEDED,
        event_type="transfer.completed",
        run_id="success-run",
        event_key="transfer-success",
        occurred_at=now,
    )
    projector.record(
        identity_id="identity-timeline",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="reconcile.library.present",
        run_id="success-run",
        event_key="library-success",
        occurred_at=now + timedelta(seconds=1),
    )
    projector.record(
        identity_id="identity-timeline",
        stage=LifecycleStage.TRANSFERRING,
        status=LifecycleStatus.FAILED,
        event_type="transfer.failed",
        run_id="stale-retry",
        event_key="stale-failure",
        occurred_at=now + timedelta(hours=1),
    )
    events = repo.list_events("identity-timeline")
    assert [event.EVENT_TYPE for event in events] == [
        "transfer.completed",
        "reconcile.library.present",
        "transfer.failed",
    ]


class TestFallbackIdentity:
    def test_prefers_anchor(self):
        from app.utils.identity import fallback_identity

        assert fallback_identity("ignored", "movie", 0, "demo_meta", "JJDA-083") == "demo_meta:JJDA-083"

    def test_uses_title_code(self):
        from app.utils.identity import fallback_identity

        assert fallback_identity("JJDA-083 Some Title", "movie") == "local:JJDA-083"

    def test_hashes_unknown_title(self):
        from app.utils.identity import fallback_identity

        first = fallback_identity("没有番号的标题", "movie")
        second = fallback_identity("没有番号的标题", "movie")
        assert first == second
        assert first.startswith("local:")

    def test_identity_fits_column_length(self):
        from app.utils.identity import fallback_identity

        for value in (
            fallback_identity("A" * 100, "movie"),
            fallback_identity("title", "movie", 0, "p" * 30, "e" * 30),
            fallback_identity("JJDA-083 title", "anime", 12),
        ):
            assert len(value) <= 26


def test_new_cycle_can_reset_terminal_stage():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    started = datetime(2026, 11, 2, 10, 0, 0)

    projector.record(
        identity_id="identity-cycle",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="reconcile.library.present",
        event_key="cycle-library",
        occurred_at=started,
    )
    projector.record(
        identity_id="identity-cycle",
        stage=LifecycleStage.DOWNLOAD_QUEUED,
        status=LifecycleStatus.QUEUED,
        event_type="download.queued",
        event_key="cycle-download-queued",
        occurred_at=started + timedelta(hours=1),
    )

    current = repo.get_current("identity-cycle")
    assert current is not None
    assert current.STAGE == LifecycleStage.DOWNLOAD_QUEUED.value
    assert current.STATUS == LifecycleStatus.QUEUED.value


def test_ensure_identity_for_ref_is_idempotent():
    from app.db.repositories.media_identity_repository import MediaIdentityRepository

    repo = MediaIdentityRepository()
    first = repo.ensure_identity_for_ref("tmdb", "12345", media_type="tv", title="Demo")
    second = repo.ensure_identity_for_ref("tmdb", "12345", media_type="tv", title="Demo")

    assert first
    assert first == second
    found = repo.find_by_ref("tmdb", "12345", media_type="tv")
    assert found is not None
    assert found.IDENTITY_ID == first


def test_find_by_title_matches_anime_and_tv():
    from app.db.repositories.media_identity_repository import MediaIdentityRepository

    repo = MediaIdentityRepository()
    identity = repo.ensure_identity(media_type="tv", title="Demo Anime", year="2026")
    anime_identity = repo.find_by_title("Demo Anime", "2026", "anime")
    tv_identity = repo.find_by_title("Demo Anime", "2026", "tv")
    assert anime_identity is not None
    assert tv_identity is not None
    assert anime_identity.IDENTITY_ID == identity.IDENTITY_ID
    assert tv_identity.IDENTITY_ID == identity.IDENTITY_ID


def test_find_by_ref_falls_back_to_other_scope():
    from app.db.repositories.media_identity_repository import MediaIdentityRepository

    repo = MediaIdentityRepository()
    identity = repo.ensure_identity(media_type="tv", title="Scoped Show", year="2026")
    repo.upsert_ref(
        identity.IDENTITY_ID,
        provider="tmdb",
        external_id="999001",
        media_type="anime",
        scope="season=1",
    )

    found = repo.find_by_ref("tmdb", "999001", media_type="tv")
    assert found is not None
    assert found.IDENTITY_ID == identity.IDENTITY_ID


def test_active_subscription_without_lifecycle_rows_is_visible():
    from app.db.repositories.base_repository import BaseRepository

    with BaseRepository().session() as db:
        db.add(
            SubscribeTvs(
                NAME="Demo Subscription",
                SEASON="S01",
                STATE="R",
                TOTAL=12,
                CURRENT_EP=6,
                LACK=7,
                IDENTITY_ID="01SUBSCRIPTION00000000001",
            )
        )
        db.commit()

    rows, total = LifecycleRepository().list_grouped(pagenum=10)

    assert total == 1
    assert rows[0]["IDENTITY_ID"] == "01SUBSCRIPTION00000000001"
    assert rows[0]["STAGE"] == LifecycleStage.SUBSCRIBED.value
    assert rows[0]["STATUS"] == LifecycleStatus.RUNNING.value
    assert rows[0]["EPISODE_COUNT"] == 12


def test_record_media_projects_each_episode():
    from app.domain.mediatypes import MediaType
    from app.media.models import MediaInfo

    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    media = MediaInfo(
        type=MediaType.TV,
        title="DEMO-EPISODE",
        begin_season=1,
        begin_episode=3,
        end_episode=4,
    )
    assert projector.record_media(
        media,
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        event_key="demo-episode",
    )
    identity_id = projector._resolver.resolve_media(media, allow_local=True).identity_id
    for episode in (3, 4):
        current = repo.get_current(identity_id, season=1, episode=episode)
        assert current is not None
        assert current.STAGE == LifecycleStage.IN_LIBRARY.value


def test_grouped_row_keeps_poster_from_episode_row():
    repo = LifecycleRepository()
    projector = LifecycleProjector(repo)
    now = datetime(2026, 11, 2, 10, 0, 0)
    projector.record(
        identity_id="poster-identity",
        stage=LifecycleStage.IN_LIBRARY,
        status=LifecycleStatus.SUCCEEDED,
        event_type="library.present",
        media_type="anime",
        season=1,
        episode=6,
        title="Poster Demo",
        poster="https://image.tmdb.org/t/p/w342/demo.jpg",
        event_key="poster-ep6",
        occurred_at=now,
    )
    projector.record(
        identity_id="poster-identity",
        stage=LifecycleStage.DOWNLOADING,
        status=LifecycleStatus.BLOCKED,
        event_type="download.blocked",
        media_type="anime",
        season=1,
        episode=0,
        title="Poster Demo",
        poster=None,
        event_key="poster-ep0-blocked",
        occurred_at=now + timedelta(minutes=5),
    )
    rows, _ = repo.list_grouped(page=1, pagenum=10)
    row = next(item for item in rows if item["IDENTITY_ID"] == "poster-identity")
    assert row["POSTER"] == "https://image.tmdb.org/t/p/w342/demo.jpg"
