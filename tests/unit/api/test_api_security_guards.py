"""API 安全防护回归测试：SSRF 拦截、配置脱敏、RBAC 越权、API Key 归属。"""

from unittest.mock import MagicMock

import pytest

from api.routers.image import _guard_image_url, _is_blocked_ip
from api.routers.rbac import _assert_role_assignment_allowed
from api.routers.system import _config_for_user, _is_sensitive_key, _mask_sensitive, _strip_masked
from app.core.exceptions import NexusError, PermissionDenied
from app.schemas.auth import SUPERADMIN_ROLE_CODE, UserContext


class TestImageSSRF:
    def test_is_blocked_ip(self):
        assert _is_blocked_ip("127.0.0.1") is True
        assert _is_blocked_ip("10.0.0.5") is True
        assert _is_blocked_ip("192.168.1.1") is True
        assert _is_blocked_ip("169.254.169.254") is True
        assert _is_blocked_ip("1.1.1.1") is False

    def test_guard_blocks_non_http_scheme(self):
        with pytest.raises(NexusError):
            _guard_image_url("file:///etc/passwd")

    def test_guard_blocks_internal_address(self, monkeypatch):
        monkeypatch.setattr(
            "api.routers.image.socket.getaddrinfo",
            lambda host, port: [(2, 1, 6, "", ("169.254.169.254", 0))],
        )
        with pytest.raises(NexusError):
            _guard_image_url("http://metadata.local/latest")

    def test_guard_allows_public_address(self, monkeypatch):
        monkeypatch.setattr(
            "api.routers.image.socket.getaddrinfo",
            lambda host, port: [(2, 1, 6, "", ("1.1.1.1", 0))],
        )
        _guard_image_url("https://example.com/a.jpg")  # 不抛


class TestConfigMasking:
    def test_sensitive_key_detection(self):
        assert _is_sensitive_key("app.login_password") is True
        assert _is_sensitive_key("app.jwt_secret") is True
        assert _is_sensitive_key("app.rmt_tmdbkey") is True
        assert _is_sensitive_key("app.tmdb_rate") is False

    def test_mask_sensitive(self):
        flat = {"app.login_password": "secret", "app.tmdb_rate": "40/m", "app.jwt_secret": ""}
        masked = _mask_sensitive(dict(flat))
        assert masked["app.login_password"] == "******"
        assert masked["app.tmdb_rate"] == "40/m"
        assert masked["app.jwt_secret"] == ""  # 空值不处理

    def test_strip_masked_dict(self):
        assert _strip_masked({"app": {"jwt_secret": "******", "keep": "1"}}) == {"app": {"keep": "1"}}

    def test_viewer_gets_masked_config(self):
        flat = {"app.rmt_tmdbkey": "tmdb-key", "app.tmdb_rate": "40/m"}
        user = UserContext(user_id=1, username="viewer", level=1, permissions=["setting:view"])
        result = _config_for_user(dict(flat), user)
        assert result["app.rmt_tmdbkey"] == "******"
        assert result["app.tmdb_rate"] == "40/m"

    def test_editor_gets_real_config(self):
        flat = {
            "app.rmt_tmdbkey": "tmdb-key",
            "laboratory.chrome_admin_token": "chrome-key",
        }
        user = UserContext(
            user_id=1,
            username="editor",
            level=0,
            permissions=["setting:view", "setting:update"],
        )
        result = _config_for_user(dict(flat), user)
        assert result["app.rmt_tmdbkey"] == "tmdb-key"
        assert result["laboratory.chrome_admin_token"] == "chrome-key"

    def test_superadmin_gets_real_config(self):
        flat = {"app.rmt_tmdbkey": "tmdb-key"}
        user = UserContext(
            user_id=1,
            username="admin",
            level=0,
            permissions=[],
            role_codes=[SUPERADMIN_ROLE_CODE],
        )
        assert _config_for_user(dict(flat), user)["app.rmt_tmdbkey"] == "tmdb-key"


class TestRbacPrivilegeGuard:
    def test_non_superadmin_cannot_grant_superadmin(self):
        svc = MagicMock()
        role = MagicMock()
        role.role_code = SUPERADMIN_ROLE_CODE
        svc.get_role_by_id.return_value = role
        user = MagicMock()
        user.is_superadmin = False
        with pytest.raises(PermissionDenied):
            _assert_role_assignment_allowed(svc, user, None, [1])

    def test_superadmin_can_grant_superadmin(self):
        svc = MagicMock()
        role = MagicMock()
        role.role_code = SUPERADMIN_ROLE_CODE
        svc.get_role_by_id.return_value = role
        user = MagicMock()
        user.is_superadmin = True
        _assert_role_assignment_allowed(svc, user, None, [1])  # 不抛

    def test_non_superadmin_cannot_modify_superadmin(self):
        svc = MagicMock()
        svc.get_role_by_id.return_value = None
        role = MagicMock()
        role.role_code = SUPERADMIN_ROLE_CODE
        svc.get_user_roles.return_value = [role]
        user = MagicMock()
        user.is_superadmin = False
        with pytest.raises(PermissionDenied):
            _assert_role_assignment_allowed(svc, user, 5, None)


class TestApiKeyOwnership:
    def test_user_can_access_key(self):
        from app.services.apikey_service import APIKeyService

        svc = APIKeyService.__new__(APIKeyService)
        repo = MagicMock()
        svc._key_repo = repo
        owner = MagicMock()
        owner.CREATED_BY = 7
        repo.get_by_id.return_value = owner

        owner_user = MagicMock()
        owner_user.is_superadmin = False
        owner_user.user_id = 7
        assert svc.user_can_access_key(1, owner_user) is True

        other_user = MagicMock()
        other_user.is_superadmin = False
        other_user.user_id = 8
        assert svc.user_can_access_key(1, other_user) is False

        superadmin = MagicMock()
        superadmin.is_superadmin = True
        assert svc.user_can_access_key(1, superadmin) is True


class TestMediaServerHostAllowlist:
    def test_configured_media_server_host_is_allowed(self, monkeypatch):
        from types import SimpleNamespace

        from api.routers import image as image_mod

        monkeypatch.setattr(image_mod, "_ms_hosts_cache", {"ts": 0.0, "hosts": set()})
        item = SimpleNamespace(CONFIG='{"host": "http://192.168.50.152:8097", "play_host": "192.168.50.152:8097"}')
        adapter = MagicMock()
        adapter.get_media_servers.return_value = [item]
        monkeypatch.setattr(image_mod, "MediaServerRepositoryAdapter", lambda: adapter)

        hosts = image_mod._allowed_media_server_hosts()
        assert "192.168.50.152" in hosts

    def test_hosts_cached_within_ttl(self, monkeypatch):
        from types import SimpleNamespace

        from api.routers import image as image_mod

        monkeypatch.setattr(image_mod, "_ms_hosts_cache", {"ts": 0.0, "hosts": set()})
        adapter = MagicMock()
        adapter.get_media_servers.return_value = [SimpleNamespace(CONFIG='{"host": "http://10.0.0.9:8096"}')]
        monkeypatch.setattr(image_mod, "MediaServerRepositoryAdapter", lambda: adapter)

        image_mod._allowed_media_server_hosts()
        image_mod._allowed_media_server_hosts()
        assert adapter.get_media_servers.call_count == 1

    def test_library_host_alias_matched_by_resolved_ip(self, monkeypatch):
        import time as _time

        from api.routers import image as image_mod

        monkeypatch.setattr(
            image_mod,
            "_ms_hosts_cache",
            {"ts": _time.time(), "hosts": {"emby.lan"}, "ips": {"192.168.50.152"}},
        )

        def _fake_getaddrinfo(host, port):
            ip = "192.168.50.152" if host == "192.168.50.152" else "10.9.9.9"
            return [(2, 1, 6, "", (ip, 0))]

        monkeypatch.setattr(image_mod.socket, "getaddrinfo", _fake_getaddrinfo)

        assert image_mod._is_allowed_library_host("emby.lan") is True
        assert image_mod._is_allowed_library_host("192.168.50.152") is True  # 别名：主机名↔IP
        assert image_mod._is_allowed_library_host("10.1.1.1") is False
