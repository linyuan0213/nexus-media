"""Agent 对话 Router 单元测试"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_app_context, get_current_user
from api.exception_handlers import register_exception_handlers
from api.routers import chat as chat_router
from app.db.models import Base
from app.db.session import Database
from app.schemas.auth import UserContext

Base.metadata.create_all(Database().engine)


def _make_client(agent_ready=True, conversation_store=None, answer="这是回答"):
    app = FastAPI()
    app.include_router(chat_router.router, prefix="/api/agent")
    admin = UserContext(user_id=1, username="admin", level=0, permissions=["agent:view"])
    app.dependency_overrides[get_current_user] = lambda: admin

    agent_service = MagicMock()
    agent_service.ready = agent_ready
    agent_service.chat_agent.chat_with_tools.return_value = answer
    ctx = SimpleNamespace(agent_service=agent_service, conversation_store=conversation_store)
    app.dependency_overrides[get_app_context] = lambda: ctx
    return TestClient(app), agent_service


class TestChatRouter:
    def test_chat_sse_stream(self):
        client, agent_service = _make_client()
        with client.stream("POST", "/api/agent/chat", json={"question": "系统状态如何"}) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())
        assert '"type": "answer"' in body
        assert "这是回答" in body

    def test_chat_empty_question(self):
        client, _ = _make_client()
        resp = client.post("/api/agent/chat", json={"question": "  "})
        assert resp.json()["code"] != 0

    def test_chat_agent_not_ready(self):
        client, _ = _make_client(agent_ready=False)
        resp = client.post("/api/agent/chat", json={"question": "你好"})
        assert resp.json()["code"] != 0

    def test_chat_clear(self):
        store = MagicMock()
        client, _ = _make_client(conversation_store=store)
        resp = client.post("/api/agent/chat/clear", json={"session_id": "s1"})
        assert resp.json()["code"] == 0
        store.clear_session.assert_called_once_with(session_id="s1", user_id="1", channel="web")

    def test_chat_clear_disabled(self):
        client, _ = _make_client(conversation_store=None)
        resp = client.post("/api/agent/chat/clear", json={"session_id": "s1"})
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["cleared"] is False

    def test_confirm_dangerous_executes(self):
        app = FastAPI()
        app.include_router(chat_router.router, prefix="/api/agent")
        admin = UserContext(user_id=1, username="admin", level=0, permissions=["agent:view", "agent:manage"])
        app.dependency_overrides[get_current_user] = lambda: admin

        executor = MagicMock()
        executor.get_schema.return_value = {"name": "subscribe_delete", "level": "dangerous"}
        executor.execute.return_value = MagicMock(success=True, data={"deleted": True})
        ctx = SimpleNamespace(agent_service=MagicMock(), conversation_store=None, tool_executor=executor)
        app.dependency_overrides[get_app_context] = lambda: ctx
        runtime = chat_router._DEFAULT_RUNTIME
        session_id = f"confirm-{uuid.uuid4().hex}"
        turn_id = runtime.start_turn(session_id, "1")
        action = runtime.create_pending(turn_id, "subscribe_delete", {"sub_id": 1}, "确认删除", "1", session_id)

        with TestClient(app) as c:
            resp = c.post("/api/agent/chat/confirm", json={"pending_action_id": action.id})
        assert resp.json()["code"] == 0
        executor.execute.assert_called_once_with(
            "subscribe_delete",
            {"sub_id": 1},
            confirmed=True,
            session_id=session_id,
            user_id="1",
            user_permissions=["agent:view", "agent:manage"],
        )

    def test_confirm_rejects_non_dangerous(self):
        app = FastAPI()
        app.include_router(chat_router.router, prefix="/api/agent")
        admin = UserContext(user_id=1, username="admin", level=0, permissions=["agent:view", "agent:manage"])
        app.dependency_overrides[get_current_user] = lambda: admin

        executor = MagicMock()
        executor.get_schema.return_value = {"name": "media_search", "level": "read"}
        ctx = SimpleNamespace(agent_service=MagicMock(), conversation_store=None, tool_executor=executor)
        app.dependency_overrides[get_app_context] = lambda: ctx
        runtime = chat_router._DEFAULT_RUNTIME
        session_id = f"reject-{uuid.uuid4().hex}"
        turn_id = runtime.start_turn(session_id, "1")
        action = runtime.create_pending(turn_id, "media_search", {"query": "x"}, "查询", "1", session_id)

        with TestClient(app) as c:
            resp = c.post("/api/agent/chat/confirm", json={"pending_action_id": action.id})
        assert resp.json()["code"] != 0
        executor.execute.assert_not_called()

    def test_confirm_requires_manage_permission(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(chat_router.router, prefix="/api/agent")
        viewer = UserContext(user_id=1, username="v", level=0, permissions=["agent:view"])
        app.dependency_overrides[get_current_user] = lambda: viewer
        with TestClient(app) as c:
            resp = c.post("/api/agent/chat/confirm", json={"pending_action_id": "x"})
        assert resp.status_code == 403

    def test_permission_denied(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(chat_router.router, prefix="/api/agent")
        guest = UserContext(user_id=2, username="guest", level=99, permissions=[])
        app.dependency_overrides[get_current_user] = lambda: guest
        with TestClient(app) as c:
            resp = c.post("/api/agent/chat", json={"question": "hi"})
        assert resp.status_code == 403

    def test_agent_status_is_lightweight(self):
        client, agent_service = _make_client()
        agent_service.provider_name = "openai"
        agent_service.model_name = "gpt-test"
        resp = client.get("/api/agent/status")
        assert resp.json()["code"] == 0
        data = resp.json()["data"]
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-test"
        assert "api_key" not in data

    def test_agent_status_exposes_configured_flag(self):
        """status 需同时暴露用户开关(configured)与可用状态(enabled)，便于前端区分三种状态."""
        client, agent_service = _make_client()
        agent_service.is_enabled = True
        data = client.get("/api/agent/status").json()["data"]
        assert data["configured"] is True
        assert data["enabled"] is True

    def test_agent_status_configured_but_not_ready(self):
        """用户启用但 Provider 未配置：configured=True、enabled=False."""
        client, agent_service = _make_client(agent_ready=False)
        agent_service.is_enabled = True
        data = client.get("/api/agent/status").json()["data"]
        assert data["configured"] is True
        assert data["enabled"] is False

    def test_agent_status_disabled(self):
        """用户未启用：configured=False、enabled=False."""
        client, agent_service = _make_client(agent_ready=False)
        agent_service.is_enabled = False
        data = client.get("/api/agent/status").json()["data"]
        assert data["configured"] is False
        assert data["enabled"] is False

    def test_cancel_turn(self):
        client, _ = _make_client()
        runtime = chat_router._DEFAULT_RUNTIME
        turn_id = runtime.start_turn("cancel-session", "1")
        resp = client.post("/api/agent/chat/cancel", json={"turn_id": turn_id})
        assert resp.json()["code"] == 0
        assert runtime.should_cancel(turn_id)
        runtime.finish_turn(turn_id, "cancelled", "cancel-session")

    def test_reject_pending_action(self):
        app = FastAPI()
        app.include_router(chat_router.router, prefix="/api/agent")
        admin = UserContext(user_id=1, username="admin", level=0, permissions=["agent:manage"])
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_app_context] = lambda: SimpleNamespace()
        runtime = chat_router._DEFAULT_RUNTIME
        turn_id = runtime.start_turn("reject-action-session", "1")
        action = runtime.create_pending(turn_id, "subscribe_delete", {}, "确认删除", "1", "reject-action-session")
        with TestClient(app) as c:
            resp = c.post("/api/agent/chat/reject", json={"pending_action_id": action.id})
        assert resp.json()["code"] == 0
        with pytest.raises(Exception):
            runtime.get_pending(action.id, "1")
