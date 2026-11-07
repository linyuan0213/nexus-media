"""生命周期时间线展示过滤测试."""

from datetime import datetime
from types import SimpleNamespace

from api.routers.lifecycle import _collapse_timeline


def test_stale_terminal_event_is_hidden_for_active_download():
    rows = [
        SimpleNamespace(STAGE="download_queued", STATUS="queued", OCCURRED_AT=datetime(2026, 11, 7, 13, 15, 27), ID=1),
        SimpleNamespace(STAGE="downloaded", STATUS="succeeded", OCCURRED_AT=datetime(2026, 11, 7, 13, 15, 28), ID=2),
        SimpleNamespace(STAGE="downloading", STATUS="running", OCCURRED_AT=datetime(2026, 11, 7, 14, 5, 48), ID=3),
    ]
    snapshot = SimpleNamespace(STAGE="downloading", STAGE_STARTED_AT=datetime(2026, 11, 7, 14, 5, 48))

    stages = [item.STAGE for item in _collapse_timeline(rows, snapshot)]

    assert "downloaded" not in stages
    assert stages == ["download_queued", "downloading"]
