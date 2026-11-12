"""SPA 签名调度：按站点配置选择专属签名器."""

from typing import Any

from app.infrastructure.http.client import HttpClient
from app.sites.providers import get_spa_signer


def spa_signed_headers(
    engine: Any,
    api: Any,
    user_config: dict,
    client: HttpClient,
    headers: dict[str, str],
    method: str,
    url: str,
    auth: Any | None = None,
) -> dict[str, str]:
    """按 auth.spa.signer 调用站点专属签名实现."""
    spa = (getattr(api, "auth", {}) or {}).get("spa") if api else None
    if not isinstance(spa, dict):
        return headers
    signer_name = str(spa.get("signer") or "").strip()
    signer = get_spa_signer(signer_name)
    if signer is None:
        raise RuntimeError(f"未配置或未注册的 SPA 签名器: {signer_name or '(空)'}")
    return signer(engine, api, user_config, client, headers, method, url, auth=auth)
