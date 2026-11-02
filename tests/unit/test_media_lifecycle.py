"""媒体生命周期读模型与状态映射测试."""

from datetime import datetime, timedelta

import pytest

from app.db.engine import get_engine
from app.db.models import Base
from app.db.models.lifecycle import MediaLifecycle
from app.db.models.subscribe import SubscribeTvs
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
    assert current.PROGRESS == 10


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


def test_grouped_incomplete_subscription_is_not_completed():
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
    assert item["STAGE"] == LifecycleStage.DOWNLOADING.value
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


def test_active_subscription_with_all_known_episodes_is_not_completed():
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
    assert rows[0]["STAGE"] == LifecycleStage.SUBSCRIBED.value
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
