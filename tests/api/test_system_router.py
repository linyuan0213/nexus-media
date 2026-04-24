"""
测试 FastAPI System Router
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.deps import (
    get_backup_restore_service,
    get_config_update_service,
    get_current_user,
    get_indexer_config_service,
    get_media_server_config_service,
    get_message_sender_service,
    get_message_service,
    get_net_test_service,
    get_progress_service,
    get_scheduler_service,
    get_system_config_service,
    get_tmdb_blacklist_helper,
    get_user_manage_service,
    get_version_service,
    get_web_search_service,
)

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestSystemRouter:
    def _mock_tmdb_helper(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_tmdb_blacklist_helper] = lambda: mock_svc
        return mock_svc

    def _teardown_tmdb(self):
        app.dependency_overrides.pop(get_tmdb_blacklist_helper, None)

    def _mock_message(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_message_service] = lambda: mock_svc
        return mock_svc

    def _teardown_message(self):
        app.dependency_overrides.pop(get_message_service, None)

    def _mock_net_test(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_net_test_service] = lambda: mock_svc
        return mock_svc

    def _teardown_net_test(self):
        app.dependency_overrides.pop(get_net_test_service, None)

    def _mock_scheduler(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_scheduler_service] = lambda: mock_svc
        return mock_svc

    def _teardown_scheduler(self):
        app.dependency_overrides.pop(get_scheduler_service, None)

    def _mock_version(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_version_service] = lambda: mock_svc
        return mock_svc

    def _teardown_version(self):
        app.dependency_overrides.pop(get_version_service, None)

    def _mock_progress(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_progress_service] = lambda: mock_svc
        return mock_svc

    def _teardown_progress(self):
        app.dependency_overrides.pop(get_progress_service, None)

    def _mock_system_config(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_system_config_service] = lambda: mock_svc
        return mock_svc

    def _teardown_system_config(self):
        app.dependency_overrides.pop(get_system_config_service, None)

    def _mock_backup(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_backup_restore_service] = lambda: mock_svc
        return mock_svc

    def _teardown_backup(self):
        app.dependency_overrides.pop(get_backup_restore_service, None)

    def _mock_user_manage(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_user_manage_service] = lambda: mock_svc
        return mock_svc

    def _teardown_user_manage(self):
        app.dependency_overrides.pop(get_user_manage_service, None)

    def _mock_config_update(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_config_update_service] = lambda: mock_svc
        return mock_svc

    def _teardown_config_update(self):
        app.dependency_overrides.pop(get_config_update_service, None)

    def _mock_indexer_config(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_indexer_config_service] = lambda: mock_svc
        return mock_svc

    def _teardown_indexer_config(self):
        app.dependency_overrides.pop(get_indexer_config_service, None)

    def _mock_media_server_config(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_media_server_config_service] = lambda: mock_svc
        return mock_svc

    def _teardown_media_server_config(self):
        app.dependency_overrides.pop(get_media_server_config_service, None)

    def _mock_message_sender(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_message_sender_service] = lambda: mock_svc
        return mock_svc

    def _teardown_message_sender(self):
        app.dependency_overrides.pop(get_message_sender_service, None)

    def _mock_web_search(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_web_search_service] = lambda: mock_svc
        return mock_svc

    def _teardown_web_search(self):
        app.dependency_overrides.pop(get_web_search_service, None)

    # ------------------------------------------------------------------
    # TmdbBlacklist
    # ------------------------------------------------------------------
    def test_add_tmdb_blacklist(self):
        mock_svc = self._mock_tmdb_helper()
        mock_svc.is_blacklisted.return_value = False
        try:
            resp = client.post("/api/system/add_tmdb_blacklist", json={
                "tmdb_id": "123", "media_type": "movie"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.add_to_blacklist.assert_called_once()
        finally:
            self._teardown_tmdb()

    def test_clear_tmdb_blacklist(self):
        mock_svc = self._mock_tmdb_helper()
        mock_svc.get_blacklist.return_value = [1]
        try:
            resp = client.post("/api/system/clear_tmdb_blacklist", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.clear_blacklist.assert_called_once()
        finally:
            self._teardown_tmdb()

    # ------------------------------------------------------------------
    # MessageClient
    # ------------------------------------------------------------------
    def test_delete_message_client(self):
        mock_svc = self._mock_message()
        mock_svc.delete_client.return_value = True
        try:
            resp = client.post("/api/system/delete_message_client", json={"cid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_client.assert_called_once_with(cid=1)
        finally:
            self._teardown_message()

    def test_get_message_client(self):
        mock_svc = self._mock_message()
        mock_svc.get_client.return_value = {"id": 1}
        try:
            resp = client.post("/api/system/get_message_client", json={"cid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["detail"] == {"id": 1}
        finally:
            self._teardown_message()

    def test_check_message_client_interactive(self):
        mock_svc = self._mock_message()
        try:
            resp = client.post("/api/system/check_message_client", json={
                "flag": "interactive", "cid": 1, "type": "tg", "checked": True
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.toggle_interactive.assert_called_once_with(
                cid=1, ctype="tg", checked=True)
        finally:
            self._teardown_message()

    def test_check_message_client_enable(self):
        mock_svc = self._mock_message()
        try:
            resp = client.post("/api/system/check_message_client", json={
                "flag": "enable", "cid": 2, "checked": True
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.toggle_enable.assert_called_once_with(cid=2, checked=True)
        finally:
            self._teardown_message()

    def test_test_message_client(self):
        mock_svc = self._mock_message()
        mock_svc.test_connection.return_value = True
        try:
            resp = client.post("/api/system/test_message_client", json={
                "type": "tg", "config": "{}"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_message()

    # ------------------------------------------------------------------
    # NetTest
    # ------------------------------------------------------------------
    def test_net_test(self):
        mock_svc = self._mock_net_test()
        mock_svc.test.return_value = MagicMock(success=True, time_ms=120)
        try:
            resp = client.post("/api/system/net_test", json={"data": "google.com"})
            assert resp.status_code == 200
            assert resp.json()["res"] is True
            assert "120 毫秒" in resp.json()["time"]
        finally:
            self._teardown_net_test()

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------
    def test_sch(self):
        mock_svc = self._mock_scheduler()
        mock_svc.start_service.return_value = (True, "服务已启动")
        try:
            resp = client.post("/api/system/sch", json={"item": "pttransfer"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["item"] == "pttransfer"
        finally:
            self._teardown_scheduler()

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------
    def test_version_has_update(self):
        mock_svc = self._mock_version()
        mock_svc.get_latest_version.return_value = MagicMock(
            has_update=True, version="3.8.0", url="http://example.com")
        try:
            resp = client.post("/api/system/version", json={})
            assert resp.status_code == 200
            assert resp.json()["version"] == "3.8.0"
        finally:
            self._teardown_version()

    def test_version_no_update(self):
        mock_svc = self._mock_version()
        mock_svc.get_latest_version.return_value = MagicMock(
            has_update=False, version="", url="")
        try:
            resp = client.post("/api/system/version", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_version()

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------
    def test_refresh_process(self):
        mock_svc = self._mock_progress()
        mock_svc.get_progress.return_value = MagicMock(
            exists=True, value=50, text="一半")
        try:
            resp = client.post("/api/system/refresh_process", json={"type": "rss"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["value"] == 50
        finally:
            self._teardown_progress()

    # ------------------------------------------------------------------
    # SystemConfig
    # ------------------------------------------------------------------
    def test_set_system_config(self):
        mock_svc = self._mock_system_config()
        mock_svc.set_config.return_value = True
        try:
            resp = client.post("/api/system/set_system_config", json={
                "key": "test_key", "value": "test_value"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_system_config()

    # ------------------------------------------------------------------
    # BackupRestore
    # ------------------------------------------------------------------
    def test_restory_backup(self):
        mock_svc = self._mock_backup()
        mock_svc.restore_from_backup.return_value = MagicMock(
            success=True, message="恢复成功")
        try:
            resp = client.post("/api/system/restory_backup", json={
                "file_name": "bk_20240101.zip"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "恢复成功"
        finally:
            self._teardown_backup()

    # ------------------------------------------------------------------
    # UserManage
    # ------------------------------------------------------------------
    def test_user_manager_add(self):
        mock_svc = self._mock_user_manage()
        mock_svc.add_user.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/system/user_manager", json={
                "oper": "add", "name": "admin", "password": "123456"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_user_manage()

    def test_user_manager_delete(self):
        mock_svc = self._mock_user_manage()
        mock_svc.delete_user.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/system/user_manager", json={
                "oper": "del", "name": "admin"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_user_manage()

    # ------------------------------------------------------------------
    # ConfigUpdate
    # ------------------------------------------------------------------
    def test_update_config(self):
        mock_svc = self._mock_config_update()
        mock_svc.update_config.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/system/update_config", json={"data": {"a": 1}})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_config_update()

    # ------------------------------------------------------------------
    # Indexer / MediaServer
    # ------------------------------------------------------------------
    def test_save_indexer_config(self):
        mock_svc = self._mock_indexer_config()
        mock_svc.save_config.return_value = MagicMock(success=True, code=0)
        try:
            resp = client.post("/api/system/save_indexer_config", json={
                "data": {"type": "builtin"}
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_indexer_config()

    def test_save_mediaserver_config(self):
        mock_svc = self._mock_media_server_config()
        mock_svc.save_config.return_value = MagicMock(success=True, code=0)
        try:
            resp = client.post("/api/system/save_mediaserver_config", json={
                "data": {"type": "emby"}
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_media_server_config()

    # ------------------------------------------------------------------
    # MessageSender
    # ------------------------------------------------------------------
    def test_send_custom_message(self):
        mock_svc = self._mock_message_sender()
        mock_svc.send_custom_message.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/system/send_custom_message", json={
                "message_clients": ["tg"], "title": "test", "text": "hello"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_message_sender()

    def test_send_plugin_message(self):
        mock_svc = self._mock_message_sender()
        try:
            resp = client.post("/api/system/send_plugin_message", json={
                "title": "test", "text": "hello"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_message_sender()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def test_search(self):
        mock_svc = self._mock_web_search()
        mock_svc.search.return_value = MagicMock(code=0, msg="")
        try:
            resp = client.post("/api/system/search", json={
                "search_word": "流浪地球", "unident": False
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_web_search()

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------
    @patch("app.utils.system_utils.SystemUtils.get_all_processes")
    def test_processes(self, mock_proc):
        mock_proc.return_value = [{"pid": 1, "name": "python"}]
        resp = client.post("/api/system/processes", json={})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"][0]["pid"] == 1
