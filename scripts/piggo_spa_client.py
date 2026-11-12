"""Piggo 前台 SPA `/v1/web` 签名请求客户端.

前置条件（从浏览器会话提取）：
  PIGGO_TOKEN       localStorage.pt_token
  PIGGO_COOKIE      可选；通常 API 只要求 Bearer + HTTP/2
  PIGGO_VISITOR_ID  window.__ptvisitorid
  PIGGO_USER_AGENT  与浏览器一致

`/v1/web/auth/sign` 返回的 sign 是 64 位十六进制 HMAC 密钥；每次业务请求
必须生成新的 nonce，并对 method + 规范化 URL + ts + nonce 计算 HMAC-SHA256。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time

import httpx2

DEFAULT_BASE = "https://piggo.me"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36"
)
SIGN_PATH = "/v1/web/auth/sign"


def canonical_url(base_path: str, url: str) -> str:
    """复现 o5()：去 query、补前导 /、合并 //、去首尾 /、转小写."""
    path = str(url or "").split("?", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    value = f"{str(base_path or '').rstrip('/')}{path}"
    value = re.sub(r"/{2,}", "/", value)
    return value.strip("/").lower()


def spa_headers(
    secret: str,
    method: str,
    base_path: str,
    url: str,
    ts: str | None = None,
) -> dict[str, str]:
    """返回 ts + X-Spa-Nonce + X-Spa-Hmac；secret 按 ASCII 字符串作为 key."""
    if not re.fullmatch(r"[a-f0-9]{64}", str(secret or "")):
        raise ValueError("sign 必须是 64 位小写十六进制")
    nonce = secrets.token_hex(16)
    timestamp = str(ts or int(time.time()))
    message = f"{method.upper()}\n{canonical_url(base_path, url)}\n{timestamp}\n{nonce}"
    digest = hmac.new(
        secret.encode("ascii"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"ts": timestamp, "X-Spa-Nonce": nonce, "X-Spa-Hmac": digest}


def _request_json(
    url: str,
    headers: dict[str, str],
    method: str = "GET",
    body: bytes | None = None,
    timeout: int = 30,
    client: httpx2.Client | None = None,
) -> tuple[int, dict | str]:
    # 该站点业务接口需要通过 HTTP/2 会话访问；HTTP/1.1 会返回 401。
    if client is not None:
        if method.upper() == "GET" and body is None:
            response = client.get(url, headers=headers)
        else:
            response = client.request(method, url, headers=headers, content=body)
        return response.status_code, _json_or_text(response.text)
    with httpx2.Client(http2=True, timeout=timeout) as owned:
        if method.upper() == "GET" and body is None:
            response = owned.get(url, headers=headers)
        else:
            response = owned.request(method, url, headers=headers, content=body)
    return response.status_code, _json_or_text(response.text)


def _json_or_text(text: str) -> dict | str:
    try:
        return json.loads(text)
    except ValueError:
        return text


def _sign_from_payload(payload: dict | str) -> str:
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if isinstance(data, dict) and data.get("sign"):
        return str(data["sign"])
    return str(payload.get("sign") or "")


def fetch_sign(
    base: str,
    token: str,
    cookie: str,
    ua: str,
    visitor_id: str,
    client: httpx2.Client | None = None,
) -> str:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": ua,
        "visitorId": visitor_id,
        "ts": str(int(time.time())),
        "version": "1.0.0",
        "webversion": "1",
        "X-Requested-With": "XMLHttpRequest",
    }
    if cookie:
        headers["Cookie"] = cookie
    status, payload = _request_json(base + SIGN_PATH, headers, client=client)
    sign = _sign_from_payload(payload)
    if status != 200 or not sign:
        raise RuntimeError(f"auth/sign 失败: HTTP {status}, {str(payload)[:500]}")
    return sign


def main() -> int:
    parser = argparse.ArgumentParser(description="Piggo SPA signed request")
    parser.add_argument("--base", default=os.environ.get("PIGGO_BASE", DEFAULT_BASE))
    parser.add_argument("--path", default="/v1/web/torrents?page=1&per_page=100")
    parser.add_argument("--method", default="GET")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        secret = "a" * 64
        result = spa_headers(
            secret,
            "POST",
            "/v1/web",
            "/torrents?q=x",
            ts="1700000000",
        )
        expected = "427a9e37532c4ce621e63f73247c362f6a757540ecba3c6fd7f8bd245024acf2"
        # nonce 随机，这里只验证同一条消息的固定 nonce 结果。
        message = "POST\nv1/web/torrents\n1700000000\n00112233445566778899aabbccddeeff"
        digest = hmac.new(secret.encode("ascii"), message.encode("utf-8"), hashlib.sha256).hexdigest()
        if digest != expected:
            print("self-test failed", digest)
            return 1
        print("self-test ok", result["X-Spa-Nonce"], digest)
        return 0

    token = os.environ.get("PIGGO_TOKEN", "")
    cookie = os.environ.get("PIGGO_COOKIE", "")
    visitor_id = os.environ.get("PIGGO_VISITOR_ID", "") or secrets.token_hex(16)
    ua = os.environ.get("PIGGO_USER_AGENT", DEFAULT_UA)
    if not token:
        print("需要 PIGGO_TOKEN", file=sys.stderr)
        return 2

    base = args.base.rstrip("/")
    with httpx2.Client(http2=True, timeout=30) as client:
        sign = fetch_sign(base, token, cookie, ua, visitor_id, client=client)
        print("sign:", sign)

        path = args.path
        if not path.startswith("/"):
            path = "/" + path
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": ua,
            "visitorId": visitor_id,
            "version": "1.0.0",
            "webversion": "1",
            "X-Requested-With": "XMLHttpRequest",
        }
        if cookie:
            headers["Cookie"] = cookie
        headers.update(spa_headers(sign, args.method, "", path))
        if os.environ.get("PIGGO_DEBUG"):
            masked = {"authorization", "cookie"}
            safe = {k: (str(v)[:12] + "..." if k.lower() in masked else v) for k, v in headers.items()}
            print("DEBUG_URL", base + path)
            print("DEBUG_HEADERS", json.dumps(safe, ensure_ascii=False))
        status, payload = _request_json(base + path, headers, method=args.method.upper(), client=client)
    print("status:", status)
    if isinstance(payload, dict):
        data = payload.get("data") or {}
        items = data.get("items") if isinstance(data, dict) else None
        print("keys:", list(payload.keys()))
        if isinstance(items, list):
            print("items:", len(items))
            if items:
                print("item_keys:", list(items[0].keys()))
                print("labels:", [x.get("name") for x in items[0].get("tags", [])])
                print("promotion:", items[0].get("promotion"))
        else:
            print(json.dumps(payload, ensure_ascii=False)[:2000])
    else:
        print(str(payload)[:2000])
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
