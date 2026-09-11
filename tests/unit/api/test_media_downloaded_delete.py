"""媒体库「近期下载」删除记录接口测试."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user, get_downloader_service
from api.exception_handlers import register_exception_handlers
from api.routers import media as media_router
from app.schemas.auth import UserContext


@pytest.fixture
def client_and_svc():
    app = FastAPI()
    app.include_router(media_router.router, prefix="/api/media")
    svc = MagicMock()
    user = UserContext(
        user_id=1,
        username="admin",
        level=0,
        permissions=["library:manage", "library:view"],
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_downloader_service] = lambda: svc
    with TestClient(app) as client:
        yield client, svc


class TestDeleteDownloaded:
    def test_delete_ok(self, client_and_svc):
        client, svc = client_and_svc
        svc.delete_download_history_by_id.return_value = True
        resp = client.post("/api/media/library/downloaded/delete", json={"history_id": 5})
        body = resp.json()
        assert body["code"] == 0
        assert body["data"] is True
        assert svc.delete_download_history_by_id.call_args.args[0] == 5

    def test_delete_not_found(self, client_and_svc):
        client, svc = client_and_svc
        svc.delete_download_history_by_id.return_value = False
        resp = client.post("/api/media/library/downloaded/delete", json={"history_id": 999})
        assert resp.json()["code"] != 0

    def test_delete_all_ok(self, client_and_svc):
        client, svc = client_and_svc
        svc.delete_all_download_history.return_value = 12
        resp = client.post("/api/media/library/downloaded/delete_all", json={})
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["count"] == 12
        svc.delete_all_download_history.assert_called_once()

    def test_delete_requires_manage_permission(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(media_router.router, prefix="/api/media")
        svc = MagicMock()
        user = UserContext(
            user_id=2,
            username="viewer",
            level=0,
            permissions=["library:view"],
        )
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_downloader_service] = lambda: svc
        with TestClient(app) as client:
            resp = client.post("/api/media/library/downloaded/delete", json={"history_id": 1})
        assert resp.status_code in (401, 403)
        svc.delete_download_history_by_id.assert_not_called()
