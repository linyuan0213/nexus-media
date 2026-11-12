"""猪猪 SPA 协议签名实现（站点专属，不放通用 HTTP 层）."""

import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from app.infrastructure.http.client import HttpClient


def signed_headers(
    engine: Any,
    api: Any,
    user_config: dict,
    client: HttpClient,
    headers: dict[str, str],
    method: str,
    url: str,
    auth: Any | None = None,
) -> dict[str, str]:
    """获取猪猪 sign 并生成 ts/nonce/HMAC 请求头."""
    spa = (getattr(api, "auth", {}) or {}).get("spa") if api else None
    if not isinstance(spa, dict):
        return headers
    prepared = dict(headers)
    prepared.setdefault("Accept", "application/json")
    prepared.setdefault("X-Requested-With", "XMLHttpRequest")
    cookie = str(user_config.get("cookie") or "").strip()
    if cookie and "Cookie" not in prepared:
        prepared["Cookie"] = cookie
    visitor_id = str(user_config.get("visitor_id") or spa.get("visitor_id") or secrets.token_hex(16))
    version = str(spa.get("version") or "1.0.0")
    webversion = str(spa.get("webversion") or "1")
    now = time.time()
    cache = getattr(engine, "_spa_sign_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(engine, "_spa_sign_cache", cache)
    cache_key = (
        str(getattr(api, "base_url", "") or ""),
        str(spa.get("sign_path") or "/v1/web/auth/sign"),
        str(prepared.get("Authorization") or ""),
        str(auth or ""),
        cookie,
    )
    cached = cache.get(cache_key)
    ttl = float(spa.get("sign_ttl") or 300)
    if not cached or now - float(cached[1]) > ttl:
        sign_headers = dict(prepared)
        sign_headers.update(
            {
                "visitorId": visitor_id,
                "ts": str(int(now)),
                "version": version,
                "webversion": webversion,
            }
        )
        sign_url = f"{str(api.base_url).rstrip('/')}{spa.get('sign_path') or '/v1/web/auth/sign'}"
        response = client.get(sign_url, headers=sign_headers, auth=auth)
        if not response.is_success:
            raise RuntimeError(f"SPA sign HTTP {response.status_code}")
        payload = response.json()
        sign = _nested_json_value(payload, str(spa.get("sign_key") or "data.sign"))
        if not sign:
            raise RuntimeError("SPA sign 响应缺少 sign")
        cached = (str(sign), now)
        cache[cache_key] = cached
    sign, _ = cached
    nonce = secrets.token_hex(16)
    timestamp = str(int(time.time()))
    canonical = urlparse(url).path.strip("/").lower()
    message = f"{method.upper()}\n{canonical}\n{timestamp}\n{nonce}"
    prepared.update(
        {
            "visitorId": visitor_id,
            "ts": timestamp,
            "version": version,
            "webversion": webversion,
            "X-Spa-Nonce": nonce,
            "X-Spa-Hmac": hmac.new(
                str(sign).encode("ascii"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest(),
        }
    )
    return prepared


def _nested_json_value(payload: Any, key: str) -> Any:
    value = payload
    for part in str(key or "").split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value
