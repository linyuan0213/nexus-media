from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._api import (
    ApiSigninHandler,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SiteSigninContext,
)


class TestApiSigninHandler:
    def _make_ctx(self, **overrides) -> SiteSigninContext:
        defaults = {
            "site": "test_site",
            "site_id": "test",
            "site_url": "https://test.site/sign",
            "cookie": "uid=1;pass=abc",
            "api_key": None,
            "bearer_token": None,
            "api_key_header": None,
            "ua": "Mozilla/5.0",
            "proxy_url": None,
            "headers": None,
            "is_browser": False,
            "raw": {},
        }
        defaults.update(overrides)
        return SiteSigninContext(**defaults)

    def test_bearer_auth_from_header_source(self):
        config = {
            "site_id": "test",
            "type": "api",
            "auth": "bearer",
            "auth_source": {"type": "header", "name": "x-sign-token"},
            "json_success_path": "code",
            "json_success_value": 0,
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(raw={"headers": {"x-sign-token": "mytoken"}})

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0}'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True

    def test_bearer_auth_missing(self):
        config = {
            "site_id": "test",
            "type": "api",
            "auth": "bearer",
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(bearer_token=None)

        result = handler.signin(ctx)
        assert result.ok is False
        assert "bearer_token" in result.msg

    def test_apikey_auth_default_header(self):
        from app.infrastructure.http.auth import ApiKeyAuth

        config = {
            "site_id": "test",
            "type": "api",
            "auth": "api_key",
            "success_markers": ["签到成功"],
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(api_key="mykey")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        call_kwargs = mock_client.post.call_args[1]
        auth = call_kwargs["auth"]
        assert isinstance(auth, ApiKeyAuth)
        assert auth._key == "X-Api-Key"
        assert auth._value == "mykey"

    def test_apikey_auth_custom_header(self):
        from app.infrastructure.http.auth import ApiKeyAuth

        config = {
            "site_id": "test",
            "type": "api",
            "auth": "api_key",
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(api_key="mykey", api_key_header="x-api-key")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            _ = handler.signin(ctx)

        call_kwargs = mock_client.post.call_args[1]
        auth = call_kwargs["auth"]
        assert isinstance(auth, ApiKeyAuth)
        assert auth._key == "x-api-key"
        assert auth._value == "mykey"

    def test_json_response_success(self):
        config = {
            "site_id": "test",
            "type": "api",
            "json_success_path": "code",
            "json_success_value": 0,
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0, "msg": "ok"}'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True

    def test_json_response_already(self):
        config = {
            "site_id": "test",
            "type": "api",
            "json_success_path": "code",
            "json_success_value": 0,
            "json_already_path": "code",
            "json_already_value": 1,
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 1, "message": "已签到"}'
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        assert "已签到" in result.msg

    def test_post_method(self):
        config = {
            "site_id": "test",
            "type": "api",
            "endpoint": {
                "method": "post",
                "path": "/sign",
                "body": {"action": "sign"},
            },
            "success_markers": ["签到成功"],
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        mock_client.post.assert_called_once()

    def test_cookie_auth_raw(self):
        config = {
            "site_id": "test",
            "type": "api",
            "auth": "cookie_raw",
            "success_markers": ["签到成功"],
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(cookie="uid=1;pass=abc")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["auth"] is not None

    def test_cookie_auth_parsed(self):
        from app.infrastructure.http.auth import CookieAuth

        config = {
            "site_id": "test",
            "type": "api",
            "auth": "cookie_parsed",
            "success_markers": ["签到成功"],
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(cookie="uid=1;pass=abc")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        call_kwargs = mock_client.post.call_args[1]
        assert isinstance(call_kwargs["auth"], CookieAuth)

    def test_unicode_escape_marker_match(self):
        """JSON 响应中包含 \\uXXXX Unicode 转义时，marker 应能正确匹配到解码后的中文。"""
        config = {
            "site_id": "test",
            "type": "api",
            "json_success_path": "status",
            "json_success_value": "1",
            "already_markers": ["已经签到", "请勿重复刷新"],
        }
        handler = ApiSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = (
            '{"status":"0","data":"\\u62b1\\u6b49",'
            '"message":"\\u60a8\\u4eca\\u5929\\u5df2\\u7ecf'
            "\\u7b7e\\u5230\\u8fc7\\u4e86\\uff0c\\u8bf7\\u52ff"
            '\\u91cd\\u590d\\u5237\\u65b0\\u3002"}'
        )
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        assert "已签到" in result.msg
