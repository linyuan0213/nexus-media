"""CookieCloud -> SPA 凭据解析测试."""

from types import SimpleNamespace
from unittest.mock import patch

from app.sites.config.credential_provider import resolve_spa_credentials


def test_cookiecloud_local_storage_wins_over_manual():
    site = SimpleNamespace(domain="piggo.me")
    user = {"api_credentials": {"spa": {"bearer_token": "manual", "visitor_id": "v1"}}}
    storage = {"pig_token": "cloud-token", "visitorId": "cloud-visitor"}
    with patch("app.sites.config.credential_provider.CookiecloudAdapter") as adapter_cls:
        adapter_cls.return_value.get_local_storage_updated_at.return_value = int(__import__("time").time())
        adapter_cls.return_value.get_cookie_updated_at.return_value = int(__import__("time").time())
        adapter_cls.return_value.get_local_storage.return_value = storage
        adapter_cls.return_value.get_cookie.return_value = "cf_clearance=x"
        spa = resolve_spa_credentials(site, user)
    assert spa.bearer_token == "cloud-token"
    assert spa.visitor_id == "cloud-visitor"
    assert spa.cookie == "cf_clearance=x"
    assert spa.source == "cookiecloud"


def test_manual_fallback_when_cookiecloud_empty():
    site = SimpleNamespace(domain="example.com")
    user = {"api_credentials": {"spa": {"bearer_token": "manual", "visitor_id": "v1"}}}
    with patch("app.sites.config.credential_provider.CookiecloudAdapter") as adapter_cls:
        adapter_cls.return_value.get_local_storage_updated_at.return_value = 0
        adapter_cls.return_value.get_cookie_updated_at.return_value = 0
        adapter_cls.return_value.get_local_storage.return_value = {}
        adapter_cls.return_value.get_cookie.return_value = ""
        spa = resolve_spa_credentials(site, user)
    assert spa.bearer_token == "manual"
    assert spa.visitor_id == "v1"
    assert spa.source == "manual"


def test_stale_cookiecloud_falls_back_to_manual():
    site = SimpleNamespace(domain="example.com")
    user = {"api_credentials": {"spa": {"bearer_token": "manual", "visitor_id": "v1"}}}
    with patch("app.sites.config.credential_provider.CookiecloudAdapter") as adapter_cls:
        adapter_cls.return_value.get_local_storage_updated_at.return_value = 1
        adapter_cls.return_value.get_cookie_updated_at.return_value = 0
        adapter_cls.return_value.get_local_storage.return_value = {"pig_token": "stale"}
        adapter_cls.return_value.get_cookie.return_value = ""
        spa = resolve_spa_credentials(site, user)
    assert spa.bearer_token == "manual"
    assert spa.source == "manual"
