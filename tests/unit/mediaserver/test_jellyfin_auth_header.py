"""Jellyfin 12 认证头兼容测试（api_key query 已废弃，需 Authorization 头）."""

from unittest.mock import MagicMock, patch

from app.mediaserver.client.jellyfin import Jellyfin


def _client(apikey: str = "KEY123") -> Jellyfin:
    client = Jellyfin.__new__(Jellyfin)
    client._host = "http://jellyfin:8096/"
    client._apikey = apikey
    client._user = "user-1"
    client._play_host = None
    return client


def test_auth_headers_format():
    assert _client()._auth_headers() == {"Authorization": 'MediaBrowser Token="KEY123"'}


def test_auth_headers_empty_without_apikey():
    assert _client(apikey="")._auth_headers() == {}


def test_requests_carry_auth_header():
    client = _client()
    with patch("app.mediaserver.client.jellyfin.HttpClient") as http_cls:
        resp = MagicMock()
        resp.json.return_value = [{"Id": "u1"}]
        http_cls.return_value.get.return_value = resp

        client.get_user_count()

    kwargs = http_cls.return_value.get.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == 'MediaBrowser Token="KEY123"'
