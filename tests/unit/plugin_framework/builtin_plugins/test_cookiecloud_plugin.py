"""CookieCloud 插件单元测试."""

from unittest.mock import MagicMock

from app.plugin_framework.builtin_plugins.cookiecloud.backend.plugin import (
    CookieCloudPlugin,
)


def _make_plugin(site_def=None, test_result=True, probe=(1.0, 10.0)):
    ctx = MagicMock()
    sync = MagicMock()
    sync.resolve_definition.return_value = site_def
    sync.test_connection.return_value = test_result
    sync.probe_domain.return_value = probe
    sync.get_credentials.return_value = {}
    plugin = CookieCloudPlugin.__new__(CookieCloudPlugin)
    plugin.ctx = ctx
    plugin._site_sync = sync
    return plugin


def _site_def(auth_type: str | None):
    return {"auth_type": auth_type or ""}


class TestVerifyCookie:
    """Cookie 校验只依赖 site_sync 端口."""

    def test_cookie_auth_site_uses_test_connection(self):
        plugin = _make_plugin(site_def=_site_def("cookie"))
        assert plugin._verify_cookie("example.com", "uid=1; pass=2") is True
        plugin._site_sync.test_connection.assert_called_once()
        user_config = plugin._site_sync.test_connection.call_args[0][1]
        assert user_config["cookie"] == "uid=1; pass=2"
        assert user_config["api_key"] == ""
        plugin._site_sync.probe_domain.assert_not_called()

    def test_no_auth_site_uses_test_connection(self):
        plugin = _make_plugin(site_def=_site_def(None))
        assert plugin._verify_cookie("example.com", "uid=1") is True
        plugin._site_sync.test_connection.assert_called_once()

    def test_csrf_auth_site_uses_test_connection(self):
        plugin = _make_plugin(site_def=_site_def("csrf"))
        assert plugin._verify_cookie("example.com", "uid=1") is True
        plugin._site_sync.test_connection.assert_called_once()

    def test_test_connection_failure_returns_false(self):
        plugin = _make_plugin(site_def=_site_def("cookie"), test_result=False)
        assert plugin._verify_cookie("example.com", "uid=1") is False

    def test_api_key_site_uses_page_probe(self):
        plugin = _make_plugin(site_def=_site_def("api_key"))
        assert plugin._verify_cookie("www.uhddolby.com", "c_secure_uid=1") is True
        plugin._site_sync.test_connection.assert_not_called()
        plugin._site_sync.probe_domain.assert_called_once_with("www.uhddolby.com", "c_secure_uid=1", attempts=1)

    def test_bearer_site_uses_page_probe(self):
        plugin = _make_plugin(site_def=_site_def("bearer"))
        assert plugin._verify_cookie("www.uhddolby.com", "uid=1") is True
        plugin._site_sync.test_connection.assert_not_called()

    def test_probe_failure_returns_false(self):
        plugin = _make_plugin(site_def=_site_def("api_key"), probe=(0.0, float("inf")))
        assert plugin._verify_cookie("www.uhddolby.com", "uid=1") is False

    def test_no_site_def_uses_page_probe(self):
        plugin = _make_plugin(site_def=None)
        assert plugin._verify_cookie("www.uhddolby.com", "uid=1") is True
        plugin._site_sync.probe_domain.assert_called_once()

    def test_exception_returns_false(self):
        plugin = _make_plugin(site_def=_site_def("api_key"))
        plugin._site_sync.probe_domain.side_effect = RuntimeError("网络异常")
        assert plugin._verify_cookie("www.uhddolby.com", "uid=1") is False


class TestCookieCloudCommand:
    """CookieCloud 消息命令处理器测试（对齐 4 参数分发约定）"""

    def test_command_triggers_manual_sync_and_feedback(self):
        plugin = _make_plugin()
        plugin._cookie_sync = MagicMock()

        plugin._on_cookiecloud_cmd("/cookiecloud", "wx", "user1", "LinYuan")

        plugin._cookie_sync.assert_called_once_with(manual=True)
        plugin.ctx._message.send_channel_msg.assert_called_once()
        _, kwargs = plugin.ctx._message.send_channel_msg.call_args
        assert kwargs.get("channel") == "wx"
        assert kwargs.get("user_id") == "user1"


class TestSpaLocalStoragePersistence:
    def test_local_storage_is_written_to_spa_credentials(self):
        plugin = _make_plugin()
        plugin._site_sync.find_sites_by_domain.return_value = [{"id": 34}]
        plugin._persist_spa_local_storage("piggo.me", "piggo.me", {"pig_token": "jwt", "visitorId": "v"})
        args, _kwargs = plugin._site_sync.upsert_credentials.call_args
        assert args[0] == 34
        assert args[1] == "spa"
        assert args[2]["source"] == "cookiecloud"
        assert args[2]["local_storage"]["pig_token"] == "jwt"


def test_spa_sync_preserves_existing_visitor_when_storage_lacks_it():
    plugin = _make_plugin()
    plugin._site_sync.find_sites_by_domain.return_value = [{"id": 34}]
    plugin._site_sync.get_credentials.return_value = {
        "spa": {
            "bearer_token": "manual-token",
            "visitor_id": "manual-visitor",
            "local_storage": {"pig_token": "manual-token"},
        }
    }
    plugin._persist_spa_local_storage("piggo.me", "piggo.me", {"pig_token": "new-token"})
    args, _ = plugin._site_sync.upsert_credentials.call_args
    assert args[2]["bearer_token"] == "new-token"
    assert args[2]["visitor_id"] == "manual-visitor"
    assert args[2]["local_storage"]["pig_token"] == "new-token"
