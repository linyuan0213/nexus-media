"""Download API Router 单元测试."""

import queue
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user
from api.routers import download as download_router
from app.schemas.auth import UserContext


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(download_router.router, prefix="/api/download")
    user_ctx = UserContext(
        user_id=1,
        username="admin",
        level=0,
        permissions=["download:view", "download:manage"],
    )
    app.dependency_overrides[get_current_user] = lambda: user_ctx
    with TestClient(app) as c:
        yield c


class TestDownloadEventsGenerator:
    def test_yields_event_data(self):
        from api.routers.download import _event_stream_generator

        q = queue.Queue()
        q.put({"event": "download.started", "data": {"title": "Test"}})

        gen = _event_stream_generator(q)
        line = next(gen)
        assert "event: download.started" in line
        assert "Test" in line

    def test_yields_keepalive_on_empty(self):
        from api.routers.download import _event_stream_generator

        mq = MagicMock()
        mq.get.side_effect = queue.Empty

        gen = _event_stream_generator(mq)
        line = next(gen)
        assert line == ": keepalive\n\n"

    def test_loops_after_keepalive(self):
        from api.routers.download import _event_stream_generator

        mq = MagicMock()
        mq.get.side_effect = [
            queue.Empty,
            {"event": "download.completed", "data": {"task_id": "1"}},
            queue.Empty,
        ]

        gen = _event_stream_generator(mq)
        assert next(gen) == ": keepalive\n\n"
        line = next(gen)
        assert "event: download.completed" in line
        assert "1" in line
        assert next(gen) == ": keepalive\n\n"


class TestDownloadEventsSSE:
    def test_auth_required(self):
        app = FastAPI()
        app.include_router(download_router.router, prefix="/api/download")
        app.state.context = MagicMock()
        with TestClient(app) as c:
            resp = c.get("/api/download/events")
        assert resp.status_code == 401

    def test_permission_required(self):
        app = FastAPI()
        app.include_router(download_router.router, prefix="/api/download")
        user_ctx = UserContext(
            user_id=2,
            username="user",
            level=0,
            permissions=[],
        )
        app.dependency_overrides[get_current_user] = lambda: user_ctx
        with TestClient(app) as c:
            resp = c.get("/api/download/events")
        assert resp.status_code == 403

    def test_returns_200_and_event_stream_type(self, client):
        with patch("api.routers.download._event_stream_generator", return_value=iter([b"data: ok\n\n"])):
            resp = client.get("/api/download/events")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        assert b"data: ok" in resp.content
