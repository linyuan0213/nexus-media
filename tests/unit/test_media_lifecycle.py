"""媒体生命周期读模型与状态映射测试."""

from datetime import datetime, timedelta

import pytest

from app.db.engine import get_engine
from app.db.models import Base
from app.db.repositories.lifecycle_repository import LifecycleRepository
from app.domain.lifecycle import (
    LifecycleStage,
    LifecycleStatus,
    map_download_state,
    map_subscribe_state,
    map_task_status,
    map_torrent_status,
)
from app.services.lifecycle_service import LifecycleProjector


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
