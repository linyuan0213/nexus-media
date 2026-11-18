"""System API Router 单元测试."""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user, get_system_config_service
from api.exception_handlers import register_exception_handlers
from api.routers import system as system_router
from app.infrastructure.progress import ProgressTracker
from app.schemas.auth import UserContext


@pytest.fixture
def client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(system_router.router, prefix="/api/v1/system")
    admin_ctx = UserContext(
        user_id=1,
        username="admin",
        level=0,
        permissions=["log:view"],
    )
    app.dependency_overrides[get_current_user] = lambda: admin_ctx
    with TestClient(app) as c:
        yield c


class TestSystemRouter:
    def test_stream_logging_missing_token(self, client):
        """缺少 token 时返回 401."""
        resp = client.get("/api/v1/system/stream-logging")
        assert resp.status_code == 401

    def test_stream_logging_invalid_token(self, client):
        """无效 token 时返回 401."""
        with patch("app.services.auth_service.AuthService.verify_token", return_value=None):
            resp = client.get("/api/v1/system/stream-logging?token=invalid")
        assert resp.status_code == 401

    def test_stream_logging_forbidden(self, client):
        """非超管且无 log:view 权限时返回 403."""
        user_ctx = UserContext(
            user_id=2,
            username="user",
            level=0,
            permissions=[],
        )
        with patch("app.services.auth_service.AuthService.verify_token", return_value=user_ctx):
            resp = client.get("/api/v1/system/stream-logging?token=valid")
        assert resp.status_code == 403

    def test_stream_logging_success(self, client):
        """有效超管 token 可建立日志流."""
        admin_ctx = UserContext(
            user_id=1,
            username="admin",
            level=0,
            permissions=["log:view"],
        )
        stream_mock = MagicMock()
        stream_mock.__iter__ = MagicMock(return_value=iter([b"data: log\n\n"]))

        with patch("app.services.auth_service.AuthService.verify_token", return_value=admin_ctx):
            with patch("api.routers.system.LogStreamingService") as mock_service_cls:
                mock_service = MagicMock()
                mock_service.stream.return_value = stream_mock
                mock_service_cls.return_value = mock_service
                resp = client.get("/api/v1/system/stream-logging?token=valid")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_search_progress_unknown_session_ends_quickly(self, client):
        """无进度记录的会话（后端重启后刷新页面）应快速关闭 SSE，而不是挂到 600s 上限."""
        start = time.monotonic()
        with client.stream("GET", f"/api/v1/system/search/progress/{uuid.uuid4()}") as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes())
        elapsed = time.monotonic() - start
        assert elapsed < 15
        assert b'"value": 100' in body
        assert b'"enable": false' in body
        assert body.endswith(b"\n\n")

    def test_search_progress_completed_session_yields_and_closes(self, client):
        """已完成的会话（enable=False 且 value=100）推送一次后立即关闭."""
        key = f"search:{uuid.uuid4()}"
        tracker = ProgressTracker()
        tracker.start(key)
        tracker.end(key)
        try:
            with client.stream("GET", f"/api/v1/system/search/progress/{key.removeprefix('search:')}") as resp:
                assert resp.status_code == 200
                body = b"".join(resp.iter_bytes())
            assert b"100" in body
        finally:
            ProgressTracker._process_detail.pop(key, None)


class TestAppearanceBackgroundRouter:
    @pytest.fixture
    def context(self, tmp_path, monkeypatch):
        saved = {}
        cfg = MagicMock()
        cfg.get.side_effect = lambda key: saved.get(key)
        cfg.set.side_effect = lambda key, value: saved.__setitem__(key, value)
        monkeypatch.setattr(system_router, "settings", SimpleNamespace(data_path=str(tmp_path)))

        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(system_router.router, prefix="/api/system")
        user = UserContext(user_id=1, username="tester", level=0, permissions=["setting:update"])
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_system_config_service] = lambda: cfg
        with TestClient(app) as client:
            yield client, cfg, saved, tmp_path

    def test_read_empty_and_save_device_urls(self, context):
        client, _cfg, saved, _tmp_path = context
        empty = client.get("/api/system/appearance/background")
        empty_slot = {"url": None, "source": None, "updated_at": None}
        assert empty.json()["data"] == {"desktop": empty_slot, "mobile": empty_slot}

        desktop = client.post(
            "/api/system/appearance/background",
            json={"url": "https://example.com/desktop.jpg", "device": "desktop"},
        )
        mobile = client.post(
            "/api/system/appearance/background",
            json={"url": "https://example.com/mobile.jpg", "device": "mobile"},
        )
        assert desktop.status_code == mobile.status_code == 200
        data = mobile.json()["data"]
        assert data["desktop"]["url"].endswith("desktop.jpg")
        assert data["mobile"]["url"].endswith("mobile.jpg")
        assert saved["appearance.background"]["desktop"]["source"] == "url"

    def test_legacy_single_background_is_desktop(self, context):
        client, _cfg, saved, _tmp_path = context
        saved["appearance.background"] = {
            "url": "/static/backgrounds/legacy.png",
            "source": "upload",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        data = client.get("/api/system/appearance/background").json()["data"]
        assert data["desktop"]["url"].endswith("/file/legacy.png")
        assert data["mobile"]["url"] is None

    def test_upload_mobile_and_clear_only_mobile(self, context):
        client, _cfg, saved, tmp_path = context
        saved["appearance.background"] = {
            "desktop": {"url": "https://example.com/desktop.jpg", "source": "url", "updated_at": None}
        }
        content = b"\x89PNG\r\n\x1a\n" + b"test-image"
        response = client.post(
            "/api/system/appearance/background/upload",
            data={"device": "mobile"},
            files={"file": ("poster.png", content, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mobile"]["source"] == "upload"
        assert data["desktop"]["url"].endswith("desktop.jpg")
        filename = data["mobile"]["url"].rsplit("/", maxsplit=1)[-1]
        assert (tmp_path / "static" / "backgrounds" / filename).read_bytes() == content

        cleared = client.delete("/api/system/appearance/background?device=mobile")
        assert cleared.json()["data"]["mobile"]["url"] is None
        assert cleared.json()["data"]["desktop"]["url"].endswith("desktop.jpg")

    def test_reject_invalid_image_and_url(self, context, monkeypatch):
        client, _cfg, _saved, _tmp_path = context
        bad_image = client.post(
            "/api/system/appearance/background/upload",
            files={"file": ("fake.png", b"not-an-image", "image/png")},
        )
        assert bad_image.json()["code"] != 0

        bad_url = client.post(
            "/api/system/appearance/background",
            json={"url": "/static/backgrounds/../../secret"},
        )
        assert bad_url.json()["code"] != 0

        monkeypatch.setattr(system_router, "_APPEARANCE_BACKGROUND_MAX_BYTES", 8)
        too_large = client.post(
            "/api/system/appearance/background/upload",
            files={"file": ("large.png", b"\x89PNG\r\n\x1a\n1", "image/png")},
        )
        assert too_large.json()["code"] != 0

    def test_write_requires_permission(self, tmp_path):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(system_router.router, prefix="/api/system")
        user = UserContext(user_id=2, username="viewer", level=0, permissions=[])
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_system_config_service] = lambda: MagicMock()
        with TestClient(app) as client:
            assert client.get("/api/system/appearance/background").status_code == 200
            assert client.post("/api/system/appearance/background", json={"url": "/static/a.png"}).status_code == 403
            assert client.delete("/api/system/appearance/background").status_code == 403
