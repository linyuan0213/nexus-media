"""站点凭据解析：API Key 与 SPA/Web 凭据分离.

API Key 只来自站点 API 凭据；SPA 凭据优先使用 CookieCloud 的
localStorage/Cookie，最后回退到 CONFIG_SITE_API_CREDENTIAL(profile=spa)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import log
from app.infrastructure.cache_system.cookiecloud_adapter import CookiecloudAdapter


@dataclass
class SpaCredentials:
    bearer_token: str = ""
    visitor_id: str = ""
    cookie: str = ""
    local_storage: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    updated_at: int = 0

    def as_config(self) -> dict[str, Any]:
        return {
            "bearer_token": self.bearer_token,
            "visitor_id": self.visitor_id,
            "cookie": self.cookie,
            "source": self.source,
        }


def _site_domains(site: Any) -> list[str]:
    if isinstance(site, str):
        raw = site
    elif isinstance(site, dict):
        raw = str(site.get("domain") or site.get("strict_url") or site.get("signurl") or "")
    else:
        raw = str(getattr(site, "domain", "") or "")
    raw = str(raw or "").strip().lower()
    if not raw:
        return []
    raw = raw.removeprefix("http://").removeprefix("https://").split("/", 1)[0]
    values = [raw]
    parts = raw.split(".")
    if len(parts) > 2:
        values.append(".".join(parts[-2:]))
    return list(dict.fromkeys(values))


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return ""


def resolve_spa_credentials(site: Any, user_config: dict | None = None) -> SpaCredentials:
    """解析站点 SPA 凭据，CookieCloud 优先，静态配置兜底."""
    config = user_config or {}
    static = (config.get("api_credentials") or {}).get("spa") or {}
    if not isinstance(static, dict):
        static = {}

    local_storage: dict[str, Any] = {}
    cookie = ""
    updated_at = 0
    max_age = int(config.get("spa_max_age") or 7 * 24 * 3600)
    now = int(time.time())
    try:
        adapter = CookiecloudAdapter()
        for domain in _site_domains(site):
            synced_at = adapter.get_local_storage_updated_at(domain)
            if synced_at and now - synced_at > max_age:
                continue
            storage = adapter.get_local_storage(domain)
            if isinstance(storage, dict) and storage:
                local_storage = storage
                updated_at = synced_at
            cookie_synced_at = adapter.get_cookie_updated_at(domain)
            if not cookie_synced_at or now - cookie_synced_at <= max_age:
                cookie = cookie or str(adapter.get_cookie(domain) or "")
            if local_storage:
                break
    except Exception as exc:  # noqa: BLE001 - CookieCloud 是可选的
        log.debug(f"[CredentialProvider]CookieCloud 不可用: {exc}")

    static_storage = static.get("local_storage")
    if not local_storage and isinstance(static_storage, dict):
        local_storage = static_storage
    token = _first_text(
        local_storage,
        ("pig_token", "auth", "token", "access_token", "accessToken"),
    )
    if not token:
        token = str(static.get("bearer_token") or static.get("token") or "")
    visitor = _first_text(
        local_storage,
        ("pig_visitorid", "visitorId", "visitor_id"),
    ) or str(static.get("visitor_id") or "")
    cookie = str(static.get("cookie") or "") or cookie
    source = "cookiecloud" if local_storage or cookie else ("manual" if static else "")
    return SpaCredentials(
        bearer_token=token,
        visitor_id=visitor,
        cookie=cookie,
        local_storage=local_storage,
        source=source,
        updated_at=updated_at,
    )


def merge_spa_config(user_config: dict, site: Any) -> dict:
    """把 SPA 凭据合并到副本，供 signer/浏览器链路使用."""
    merged = dict(user_config or {})
    spa = resolve_spa_credentials(site, merged)
    if spa.bearer_token:
        merged["bearer_token"] = spa.bearer_token
    if spa.visitor_id:
        merged["visitor_id"] = spa.visitor_id
    if spa.cookie:
        merged["cookie"] = spa.cookie
    merged["spa_source"] = spa.source
    merged["local_storage"] = spa.local_storage
    return merged
