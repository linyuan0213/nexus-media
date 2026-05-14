"""
测试 FastAPI 认证依赖
"""
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from api.deps import get_current_user

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key="test-secret",
    session_cookie="session",
)


@app.get("/whoami")
def whoami(user=Depends(get_current_user)):
    return {"user": user}


client = TestClient(app)


def test_whoami_no_auth_returns_401():
    resp = client.get("/whoami")
    assert resp.status_code == 401
    assert "安全认证未通过" in resp.json()["detail"]


@patch("api.deps.Config")
def test_whoami_with_api_key_query_param(mock_config_cls):
    mock_config = MagicMock()
    mock_config.get_config.return_value = {"api_key": "test-api-key-123"}
    mock_config_cls.return_value = mock_config

    resp = client.get("/whoami", params={"apikey": "test-api-key-123"})
    assert resp.status_code == 200
    result = resp.json()["user"]
    # 现在返回 UserContext，兼容字符串和对象
    if isinstance(result, dict):
        assert result["username"] == "api"
    else:
        assert result == "api"
