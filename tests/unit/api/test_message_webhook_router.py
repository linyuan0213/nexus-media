"""Message webhook router 单元测试."""

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_app_context, get_message
from api.routers import message_webhook as webhook_router
from app.message import Message


def _build_mock_message(verify_url_return: Any = b"plain_echostr", parse_message_return: Any = None):
    mock_client = MagicMock()
    mock_client.get_webhook_allow_ip.return_value = {"ipv4": "0.0.0.0/0", "ipv6": "::/0"}
    mock_client.verify_url.return_value = verify_url_return
    mock_client.parse_message.return_value = parse_message_return

    mock_message = MagicMock(spec=Message)
    mock_message.get_interactive_client.return_value = {"client": mock_client}
    mock_message.active_clients = []

    return mock_message, mock_client


class TestWeChatWebhookRouter:
    """企业微信回调路由测试."""

    def _make_app(self, mock_message, app_context):
        app = FastAPI()
        app.include_router(webhook_router.router)
        app.dependency_overrides[get_app_context] = lambda: app_context
        app.dependency_overrides[get_message] = lambda: mock_message
        return app

    def test_wechat_verify_uses_msg_signature(self):
        """加密模式下企业微信使用 msg_signature 参数验证 URL."""
        mock_message, mock_client = _build_mock_message(verify_url_return=b"decrypted")
        app = self._make_app(mock_message, MagicMock())

        with TestClient(app) as tc:
            resp = tc.get("/wechat?signature=plain_sig&msg_signature=msg_sig&timestamp=123&nonce=abc&echostr=xxx")
        assert resp.status_code == 200
        assert resp.content == b"decrypted"
        mock_client.verify_url.assert_called_once_with("msg_sig", "123", "abc", "xxx")

    def test_wechat_verify_falls_back_to_signature(self):
        """明文模式下企业微信使用 signature 参数验证 URL."""
        mock_message, mock_client = _build_mock_message(verify_url_return=b"plain_echostr")
        app = self._make_app(mock_message, MagicMock())

        with TestClient(app) as tc:
            resp = tc.get("/wechat?signature=plain_sig&timestamp=123&nonce=abc&echostr=hello")
        assert resp.status_code == 200
        assert resp.content == b"plain_echostr"
        mock_client.verify_url.assert_called_once_with("plain_sig", "123", "abc", "hello")

    def test_wechat_webhook_uses_msg_signature(self):
        """加密模式下 POST 消息使用 msg_signature 参数."""
        mock_message, mock_client = _build_mock_message(
            parse_message_return={
                "FromUserName": "from_user",
                "Content": "hello",
            }
        )
        app = self._make_app(mock_message, MagicMock())

        with (
            patch("api.routers.message_webhook.MessageSearchService"),
            patch("api.routers.message_webhook.MessageCommandHandler") as mock_handler_cls,
        ):
            with TestClient(app) as tc:
                resp = tc.post(
                    "/wechat?signature=plain_sig&msg_signature=msg_sig&timestamp=123&nonce=abc",
                    content="<xml><Encrypt>encrypted</Encrypt></xml>",
                )
        assert resp.status_code == 200
        assert resp.text == "success"
        mock_client.parse_message.assert_called_once_with(
            "<xml><Encrypt>encrypted</Encrypt></xml>", signature="msg_sig", timestamp="123", nonce="abc"
        )
        mock_handler_cls.return_value.handle_message_job.assert_called_once()

    def test_wechat_verify_signature_failure(self):
        """签名验证失败返回 403."""
        mock_message, mock_client = _build_mock_message(verify_url_return=None)
        app = self._make_app(mock_message, MagicMock())

        with TestClient(app) as tc:
            resp = tc.get("/wechat?msg_signature=bad_sig&timestamp=123&nonce=abc&echostr=xxx")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "WeChat signature verification failed"

    def test_wechat_client_not_configured(self):
        """未配置交互式微信客户端返回 404."""
        mock_message = MagicMock(spec=Message)
        mock_message.get_interactive_client.return_value = None
        mock_message.active_clients = []
        app = self._make_app(mock_message, MagicMock())

        with TestClient(app) as tc:
            resp = tc.get("/wechat?msg_signature=sig&timestamp=123&nonce=abc&echostr=xxx")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "WeChat client not configured"
