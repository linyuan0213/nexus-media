"""qBittorrent API Key 认证测试."""

from unittest.mock import MagicMock, patch

from app.downloader.client.qbittorrent import Qbittorrent


def _client(api_key=None):
    client = Qbittorrent.__new__(Qbittorrent)
    client.client_name = "Qbittorrent"
    client.name = "qB-api-key"
    client.host = "127.0.0.1"
    client.port = 8080
    client.username = None
    client.password = None
    client.api_key = api_key
    return client


def test_api_key_is_passed_to_qbittorrent_client():
    qb = _client("qb-secret-key")
    qbc = MagicMock()
    qbc.app_version.return_value = "v5.2.3"

    with patch("qbittorrentapi.Client", return_value=qbc) as client_cls:
        login = getattr(qb, "_Qbittorrent__login_qbittorrent")
        assert login() is qbc

    kwargs = client_cls.call_args.kwargs
    assert kwargs["api_key"] == "qb-secret-key"
    assert kwargs["username"] is None
    assert kwargs["password"] is None
    qbc.auth_log_in.assert_called_once()


def test_password_mode_passes_none_api_key():
    qb = _client()
    qbc = MagicMock()
    qbc.app_version.return_value = "v4.6.7"

    with patch("qbittorrentapi.Client", return_value=qbc) as client_cls:
        login = getattr(qb, "_Qbittorrent__login_qbittorrent")
        login()

    assert client_cls.call_args.kwargs["api_key"] is None


def test_api_key_field_is_optional_in_schema():
    fields = {field.id: field for field in Qbittorrent.config_schema.fields}

    assert "api_key" in fields
    assert fields["api_key"].required is False
    assert fields["api_key"].type == "password"
    assert fields["username"].required is False
