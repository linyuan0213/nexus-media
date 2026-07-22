from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers._api import (
    ApiRssGenHandler,
)
from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenContext,
)


class TestApiRssGenHandler:
    def _make_ctx(self, **overrides) -> SiteRssGenContext:
        defaults = {
            "site": "test_site",
            "site_id": "test",
            "site_url": "https://test.site/rss",
            "cookie": None,
            "api_key": None,
            "bearer_token": None,
            "api_key_header": None,
            "ua": "Mozilla/5.0",
            "proxy_url": None,
            "headers": None,
            "raw": {"id": 1},
        }
        defaults.update(overrides)
        return SiteRssGenContext(**defaults)

    def test_json_rss_link_success(self):
        config = {
            "site_id": "test",
            "type": "api",
            "endpoint": {"path": "/api/rss/genlink", "method": "post"},
            "json_rss_link_path": "data.dlUrl",
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"data": {"dlUrl": "https://test.site/rss/1"}}'
        mock_client.post.return_value = mock_res

        mock_repo = MagicMock()
        handler._site_repo = mock_repo

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is True
        mock_repo.update_site_rssurl.assert_called_once_with(1, "https://test.site/rss/1")

    def test_json_success_marker(self):
        config = {
            "site_id": "test",
            "type": "api",
            "endpoint": {"path": "/api/rss", "method": "post"},
            "json_success_path": "code",
            "json_success_value": 0,
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0, "msg": "ok"}'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is True

    def test_api_key_auth(self):
        from app.infrastructure.http.auth import ApiKeyAuth

        config = {
            "site_id": "test",
            "type": "api",
            "endpoint": {"path": "/api/rss", "method": "post"},
            "auth": "api_key",
            "json_success_path": "code",
            "json_success_value": 0,
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx(api_key="mykey", api_key_header="x-api-key")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0}'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is True
        call_kwargs = mock_client.post.call_args[1]
        auth = call_kwargs["auth"]
        assert isinstance(auth, ApiKeyAuth)
        assert auth._key == "x-api-key"
        assert auth._value == "mykey"

    def test_bearer_auth_missing(self):
        config = {
            "site_id": "test",
            "type": "api",
            "auth": "bearer",
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx(bearer_token=None)

        result = handler.generate(ctx)
        assert result.ok is False
        assert "bearer_token" in result.msg

    def test_cookie_auth(self):
        config = {
            "site_id": "test",
            "type": "api",
            "auth": "cookie",
            "json_success_path": "code",
            "json_success_value": 0,
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx(cookie="uid=1;pass=abc")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0}'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is True
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["auth"] is not None

    def test_api_request_failure(self):
        config = {
            "site_id": "test",
            "type": "api",
            "endpoint": {"path": "/api/rss", "method": "post"},
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("connection failed")

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "请检查站点连通性" in result.msg

    def test_invalid_json(self):
        config = {
            "site_id": "test",
            "type": "api",
            "endpoint": {"path": "/api/rss", "method": "post"},
            "json_success_path": "code",
        }
        handler = ApiRssGenHandler(MagicMock(), None, None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "not json"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.generate(ctx)

        assert result.ok is False
        assert "解析JSON" in result.msg
