"""
测试 FastAPI System Router — 设置页面相关接口补充测试
覆盖基础设置、消息通知、索引器、媒体服务器配置等接口
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import (
    get_config_update_service,
    get_current_user,
    get_indexer_config_service,
    get_media_server_config_service,
    get_message_service,
    get_system_config_service,
)
from api.main import app

app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestSystemConfigEndpoints:
    """测试系统配置更新接口"""

    def _mock_config_update(self):
        mock_svc = MagicMock()
        result = MagicMock()
        result.success = True
        mock_svc.update_config.return_value = result
        app.dependency_overrides[get_config_update_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_config_update_service, None)

    def test_update_config_success(self):
        self._mock_config_update()
        resp = client.post(
            "/api/system/config/update",
            json={
                "data": {
                    "app.wallpaper": "bing",
                    "app.web_port": "3000",
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        self._teardown()

    def test_set_system_config(self):
        mock_svc = MagicMock()
        mock_svc.set_config.return_value = True
        app.dependency_overrides[get_system_config_service] = lambda: mock_svc
        resp = client.post(
            "/api/system/config",
            json={
                "key": "DefaultDownloader",
                "value": "qbittorrent",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        app.dependency_overrides.pop(get_system_config_service, None)


class TestMessageClientEndpoints:
    """测试消息客户端接口"""

    def _mock_message(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_message_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_message_service, None)

    def test_get_message_client(self):
        svc = self._mock_message()
        svc.get_client.return_value = {"id": 1, "name": "Test"}
        resp = client.post("/api/system/message_clients", json={"cid": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        self._teardown()

    def test_update_message_client(self):
        svc = self._mock_message()
        resp = client.post(
            "/api/system/message_clients/update",
            json={
                "cid": None,
                "name": "TestBot",
                "type": "telegram",
                "config": "{}",
                "switchs": "download_start,transfer_finished",
                "interactive": 1,
                "enabled": 1,
                "templates": "{}",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        svc.upsert_client.assert_called_once()
        self._teardown()

    def test_delete_message_client(self):
        svc = self._mock_message()
        svc.delete_client.return_value = True
        resp = client.post("/api/system/message_clients/delete", json={"cid": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        self._teardown()

    def test_test_message_client(self):
        svc = self._mock_message()
        svc.test_connection.return_value = True
        resp = client.post(
            "/api/system/message_clients/test",
            json={
                "type": "telegram",
                "config": "{}",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        self._teardown()

    def test_send_custom_message(self):
        self._mock_message()
        with patch("api.routers.system.MessageSenderService") as mock_sender_cls:
            mock_sender = MagicMock()
            result = MagicMock()
            result.success = True
            mock_sender.send_custom_message.return_value = result
            mock_sender_cls.return_value = mock_sender
            resp = client.post(
                "/api/system/messages/send",
                json={
                    "title": "测试消息",
                    "text": "内容",
                    "image": "",
                    "message_clients": ["1"],
                },
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        self._teardown()


class TestIndexerConfigEndpoints:
    """测试索引器配置接口"""

    def _mock_indexer(self):
        mock_svc = MagicMock()
        result = MagicMock()
        result.success = True
        result.code = 0
        mock_svc.save_config.return_value = result
        app.dependency_overrides[get_indexer_config_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_indexer_config_service, None)

    def test_save_indexer_config(self):
        self._mock_indexer()
        resp = client.post(
            "/api/system/indexers/config",
            json={
                "data": {
                    "type": "builtin",
                    "indexer_sites": ["site1", "site2"],
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        self._teardown()


class TestMediaServerConfigEndpoints:
    """测试媒体服务器配置接口"""

    def _mock_mediaserver(self):
        mock_svc = MagicMock()
        result = MagicMock()
        result.success = True
        result.code = 0
        mock_svc.save_config.return_value = result
        app.dependency_overrides[get_media_server_config_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_media_server_config_service, None)

    def test_save_mediaserver_config(self):
        self._mock_mediaserver()
        resp = client.post(
            "/api/system/mediaservers/config",
            json={
                "data": {
                    "type": "emby",
                    "host": "127.0.0.1",
                    "port": "8096",
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        self._teardown()
