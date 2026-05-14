"""
测试 /message WebSocket 端点
"""

import pytest
from fastapi.testclient import TestClient

from api.deps import get_current_user
from api.main import app
from api.routers.pages import utils_routes
from app.schemas.auth import UserContext

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: UserContext(
    user_id=1, username="testuser", level=0, permissions=[], is_superadmin=False
)
client = TestClient(app)


def _mock_get_ws_user(_websocket):
    return UserContext(user_id=1, username="testuser", level=0, permissions=[], is_superadmin=False)


class TestMessageWebSocket:
    def test_websocket_connect_and_get_messages(self, monkeypatch):
        """测试 WebSocket 连接并获取系统消息"""
        monkeypatch.setattr(utils_routes, "_get_ws_user", _mock_get_ws_user)
        with client.websocket_connect("/message") as ws:
            ws.send_json({"lst_time": ""})
            data = ws.receive_json()
            assert data["code"] == 0
            assert "message" in data
            assert "lst_time" in data

    def test_websocket_unauthorized_without_session(self, monkeypatch):
        """无认证时应被拒绝"""
        monkeypatch.setattr(utils_routes, "_get_ws_user", lambda _w: None)
        with pytest.raises(Exception), client.websocket_connect("/message"):
            pass
