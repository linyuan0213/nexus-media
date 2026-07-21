"""Telegram 消息客户端单元测试."""

from unittest.mock import MagicMock, patch

from app.message.client.telegram import Telegram


class TestTelegramWebhook:
    """测试 Telegram Webhook 配置."""

    def test_webhook_url_is_set(self):
        """read_config 应正确构造 _webhook_url."""
        apikey_service = MagicMock()
        apikey_service.get_or_create_system_key.return_value = "test_api_key"
        client = Telegram(
            {"token": "bot_token", "chat_id": "12345", "webhook": True},
            apikey_service=apikey_service,
        )
        assert client._webhook_url is not None
        assert client._webhook_url.endswith("/telegram?apikey=test_api_key")

    def test_set_webhook_includes_secret_token(self):
        """配置 secret_token 时 setWebhook 请求应携带 secret_token."""
        apikey_service = MagicMock()
        apikey_service.get_or_create_system_key.return_value = "test_api_key"
        client = Telegram(
            {
                "token": "bot_token",
                "chat_id": "12345",
                "webhook": True,
                "secret_token": "my_secret",
            },
            apikey_service=apikey_service,
        )
        Telegram._setup_done = set()

        responses = [
            {"ok": True, "result": {"url": "https://old.url/telegram"}},  # getWebhookInfo
            {"ok": True},  # deleteWebhook
            {"ok": True},  # setWebhook
        ]
        with (
            patch("app.message.client.telegram.HttpClient") as mock_http,
            patch("app.message.client.telegram._webhook_set", False),
        ):
            mock_req = MagicMock()
            mock_req.get.return_value.json.side_effect = responses
            mock_http.return_value = mock_req
            client._set_webhook()

        calls = mock_req.get.call_args_list
        assert len(calls) == 3
        set_webhook_url = calls[2].kwargs.get("url") or calls[2].args[0]
        assert "secret_token=my_secret" in set_webhook_url

    def test_set_webhook_without_secret_token(self):
        """未配置 secret_token 时 setWebhook 请求不应携带 secret_token."""
        apikey_service = MagicMock()
        apikey_service.get_or_create_system_key.return_value = "test_api_key"
        client = Telegram(
            {"token": "bot_token", "chat_id": "12345", "webhook": True},
            apikey_service=apikey_service,
        )
        Telegram._setup_done = set()

        responses = [
            {"ok": True, "result": {"url": "https://old.url/telegram"}},
            {"ok": True},
            {"ok": True},
        ]
        with (
            patch("app.message.client.telegram.HttpClient") as mock_http,
            patch("app.message.client.telegram._webhook_set", False),
        ):
            mock_req = MagicMock()
            mock_req.get.return_value.json.side_effect = responses
            mock_http.return_value = mock_req
            client._set_webhook()

        calls = mock_req.get.call_args_list
        assert len(calls) == 3
        set_webhook_url = calls[2].kwargs.get("url") or calls[2].args[0]
        assert "secret_token" not in set_webhook_url
