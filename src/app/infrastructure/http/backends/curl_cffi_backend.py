"""curl_cffi HTTP backend：用浏览器 TLS 指纹访问 WAF 站点.

只负责传输；重试、限流、缓存仍由 HttpClient/AsyncHttpClient 负责。
"""

from __future__ import annotations

from typing import Any, cast

import httpx2

import log
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpConnectionError

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - 可选依赖缺失时由 HttpClient 报告
    curl_requests = None


def _is_available() -> bool:
    return curl_requests is not None


def _build_headers(config: HttpClientConfig, kwargs: dict[str, Any]) -> dict[str, str]:
    headers = dict(config.default_headers or {})
    headers.update(kwargs.pop("headers", {}) or {})
    return headers


def _response_from_curl(curl_response: Any, method: str, requested_url: str) -> httpx2.Response:
    """把 curl_cffi 响应转换为 httpx2.Response，保持现有调用方接口."""
    content = curl_response.content
    if isinstance(content, str):
        content = content.encode()
    final_url = str(getattr(curl_response, "url", "") or requested_url)
    headers = dict(getattr(curl_response, "headers", {}) or {})
    request = httpx2.Request(method.upper(), final_url, headers=headers)
    response = httpx2.Response(
        status_code=int(curl_response.status_code),
        headers=headers,
        content=content,
        request=request,
    )
    return response


def _profiles(requested: str | None) -> list[str | None]:
    primary = requested or "chrome"
    ordered: list[str | None] = [primary]
    # chrome/chrome1xx 会请求当前 BoringSSL 不支持的 PQ 曲线，回退到稳定的
    # Chrome 124 profile；再失败则使用 libcurl 默认 TLS。
    for fallback in ("chrome124", None):
        if fallback not in ordered:
            ordered.append(fallback)
    return ordered


def _can_retry_profile(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "openssl_internal" in text or "invalid library" in text


class CurlCffiBackend:
    """同步 curl_cffi backend，响应缓冲为 httpx2.Response."""

    def __init__(self, config: HttpClientConfig):
        if not _is_available():
            raise HttpConnectionError("curl_cffi 未安装，无法使用 curl_cffi backend")
        self._config = config
        self._profiles = _profiles(config.impersonate)
        self._profile_index = 0
        self._session = self._new_session(self._profiles[0])

    def _new_session(self, profile: str | None) -> Any:
        session_kwargs: dict[str, Any] = {
            "impersonate": profile,
            "verify": self._config.verify_ssl,
            "timeout": self._config.timeout,
        }
        if self._config.proxy_url:
            session_kwargs["proxy"] = self._config.proxy_url
        if self._config.default_headers:
            session_kwargs["headers"] = dict(self._config.default_headers)
        return cast(Any, curl_requests).Session(**session_kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx2.Response:
        request_kwargs = dict(kwargs)
        request_kwargs.pop("follow_redirects", None)
        request_kwargs.pop("raise_for_status", None)
        request_kwargs.pop("allow_redirects", None)
        request_kwargs["allow_redirects"] = self._config.follow_redirects
        request_kwargs["headers"] = _build_headers(self._config, request_kwargs)
        request_kwargs["timeout"] = request_kwargs.get("timeout") or self._config.timeout
        while True:
            try:
                raw = self._session.request(cast(Any, method.upper()), url, **request_kwargs)
                break
            except Exception as exc:
                if _can_retry_profile(exc) and self._profile_index + 1 < len(self._profiles):
                    self._profile_index += 1
                    try:
                        self._session.close()
                    except Exception as close_exc:
                        log.debug(f"[CurlCffiBackend] 关闭旧 session 失败: {close_exc}")
                    self._session = self._new_session(self._profiles[self._profile_index])
                    log.warn(f"[CurlCffiBackend] TLS profile 回退: {self._profiles[self._profile_index]!r} url={url}")
                    continue
                # 统一成 httpx 连接异常，交给现有 retry/错误映射处理。
                raise httpx2.ConnectError(str(exc), request=httpx2.Request(method, url)) from exc
        content = raw.content or b""
        if self._config.max_buffered_size and len(content) > self._config.max_buffered_size:
            raise HttpConnectionError(
                f"curl_cffi 响应超过缓冲上限 {self._config.max_buffered_size} bytes，请使用 httpx backend"
            )
        return _response_from_curl(raw, method, url)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[CurlCffiBackend] close 失败: {exc}")


class AsyncCurlCffiBackend:
    """异步 curl_cffi backend."""

    def __init__(self, config: HttpClientConfig):
        if not _is_available():
            raise HttpConnectionError("curl_cffi 未安装，无法使用 curl_cffi backend")
        self._config = config
        self._profiles = _profiles(config.impersonate)
        self._profile_index = 0
        self._session = self._new_session(self._profiles[0])

    def _new_session(self, profile: str | None) -> Any:
        session_kwargs: dict[str, Any] = {
            "impersonate": profile,
            "verify": self._config.verify_ssl,
            "timeout": self._config.timeout,
        }
        if self._config.proxy_url:
            session_kwargs["proxy"] = self._config.proxy_url
        if self._config.default_headers:
            session_kwargs["headers"] = dict(self._config.default_headers)
        return cast(Any, curl_requests).AsyncSession(**session_kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx2.Response:
        request_kwargs = dict(kwargs)
        request_kwargs.pop("follow_redirects", None)
        request_kwargs.pop("raise_for_status", None)
        request_kwargs.pop("allow_redirects", None)
        request_kwargs["allow_redirects"] = self._config.follow_redirects
        request_kwargs["headers"] = _build_headers(self._config, request_kwargs)
        request_kwargs["timeout"] = request_kwargs.get("timeout") or self._config.timeout
        while True:
            try:
                raw = await self._session.request(cast(Any, method.upper()), url, **request_kwargs)
                break
            except Exception as exc:
                if _can_retry_profile(exc) and self._profile_index + 1 < len(self._profiles):
                    self._profile_index += 1
                    try:
                        await self._session.close()
                    except Exception as close_exc:
                        log.debug(f"[AsyncCurlCffiBackend] 关闭旧 session 失败: {close_exc}")
                    self._session = self._new_session(self._profiles[self._profile_index])
                    log.warn(
                        f"[AsyncCurlCffiBackend] TLS profile 回退: {self._profiles[self._profile_index]!r} url={url}"
                    )
                    continue
                raise httpx2.ConnectError(str(exc), request=httpx2.Request(method, url)) from exc
        content = raw.content or b""
        if self._config.max_buffered_size and len(content) > self._config.max_buffered_size:
            raise HttpConnectionError(
                f"curl_cffi 响应超过缓冲上限 {self._config.max_buffered_size} bytes，请使用 httpx backend"
            )
        return _response_from_curl(raw, method, url)

    async def close(self) -> None:
        try:
            await self._session.close()
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[AsyncCurlCffiBackend] close 失败: {exc}")

    async def aclose(self) -> None:
        await self.close()
