from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._declarative import (
    DeclarativeSigninHandler,
    DeclarativeSiteConfig,
)
from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SiteSigninContext,
)


class TestDeclarativeSigninHandler:
    def _make_ctx(self, **overrides) -> SiteSigninContext:
        defaults = {
            "site": "test_site",
            "site_url": "https://test.site/sign",
            "cookie": "uid=1;pass=abc",
            "api_key": None,
            "bearer_token": None,
            "api_key_header": None,
            "ua": "Mozilla/5.0",
            "proxy_url": None,
            "headers": None,
            "is_chrome": False,
            "raw": {},
        }
        defaults.update(overrides)
        return SiteSigninContext(**defaults)

    def test_default_cookie_auth(self):
        config = DeclarativeSiteConfig(site_url="test.site", success_markers=["签到成功"])
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        mock_client.get.assert_called_once()

    def test_bearer_auth_from_header_source(self):
        config = DeclarativeSiteConfig(
            site_url="test.site",
            auth_type="bearer",
            auth_source={"type": "header", "name": "x-sign-token"},
            response_type="json",
            json_success_path="code",
            json_success_value=0,
        )
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(raw={"headers": {"x-sign-token": "mytoken"}})

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0}'
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True

    def test_bearer_auth_missing(self):
        config = DeclarativeSiteConfig(
            site_url="test.site",
            auth_type="bearer",
        )
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(bearer_token=None)

        result = handler.signin(ctx)
        assert result.ok is False
        assert "bearer_token" in result.msg

    def test_apikey_auth_default_header(self):
        config = DeclarativeSiteConfig(
            site_url="test.site",
            auth_type="apikey",
            success_markers=["签到成功"],
        )
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(api_key="mykey")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["headers"]["X-Api-Key"] == "mykey"

    def test_apikey_auth_custom_header(self):
        config = DeclarativeSiteConfig(
            site_url="test.site",
            auth_type="apikey",
        )
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx(api_key="mykey", api_key_header="x-api-key")

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            _ = handler.signin(ctx)

        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["headers"]["x-api-key"] == "mykey"

    def test_json_response_success(self):
        config = DeclarativeSiteConfig(
            site_url="test.site",
            response_type="json",
            json_success_path="code",
            json_success_value=0,
        )
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = '{"code": 0, "msg": "ok"}'
        mock_client.get.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True

    def test_post_method(self):
        config = DeclarativeSiteConfig(
            site_url="test.site",
            method="post",
            data={"action": "sign"},
            success_markers=["签到成功"],
        )
        handler = DeclarativeSigninHandler(MagicMock(), None, config)
        ctx = self._make_ctx()

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.text = "签到成功"
        mock_client.post.return_value = mock_res

        with patch.object(handler, "_http_client", return_value=mock_client):
            result = handler.signin(ctx)

        assert result.ok is True
        mock_client.post.assert_called_once()
