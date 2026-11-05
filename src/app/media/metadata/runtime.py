"""Provider 运行时：按 provider 的限流、熔断、URL 安全校验与健康统计."""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.infrastructure.rate_limiter.backends import RateLimitEngine

from .errors import ProviderRateLimited, ProviderUnavailable
from .models import ProviderDescriptor


class UnsafeProviderURL(ValueError):
    pass


_rate_engine: RateLimitEngine | None = None
_rate_engine_lock = threading.Lock()


def _shared_rate_engine() -> RateLimitEngine:
    """Redis 可用时跨实例共享元数据限流；否则退化为内存令牌桶."""
    global _rate_engine
    if _rate_engine is None:
        with _rate_engine_lock:
            if _rate_engine is None:
                _rate_engine = RateLimitEngine()
    return _rate_engine


def validate_outbound_url(url: str, allowed_hosts: frozenset[str] = frozenset()) -> str:
    """只允许 http/https，拒绝内网/回环/链路本地地址与未声明域名."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeProviderURL(f"非法 provider URL: {url}")
    host = parsed.hostname.lower()
    if allowed_hosts and host not in {item.lower() for item in allowed_hosts}:
        raise UnsafeProviderURL(f"域名未在 allowed_hosts 声明: {host}")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port or 443)}
    except socket.gaierror as exc:
        raise UnsafeProviderURL(f"域名解析失败: {host}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeProviderURL(f"拒绝访问内网地址: {address}")
    return url


@dataclass
class ProviderContext:
    """传给 provider 的运行时上下文."""

    descriptor: ProviderDescriptor
    runtime: "ProviderRuntime"
    cache: dict = field(default_factory=dict)

    def validate_url(self, url: str) -> str:
        return validate_outbound_url(url, self.descriptor.allowed_hosts)


@dataclass
class ProviderRuntime:
    descriptor: ProviderDescriptor
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_call: float = 0.0
    _failures: int = 0
    _open_until: float = 0.0
    _success: int = 0
    _failure: int = 0
    cache: dict[str, object] = field(default_factory=dict)

    def acquire(self) -> None:
        now = time.monotonic()
        with self._lock:
            if now < self._open_until:
                raise ProviderUnavailable(
                    self.descriptor.provider_key,
                    f"provider 熔断中，剩余 {int(self._open_until - now)}s",
                )
        rpm = int(self.descriptor.rate_limit_per_minute or 0)
        if rpm <= 0:
            return
        interval = 60.0 / rpm
        try:
            engine = _shared_rate_engine()
            acquired = engine.acquire(
                f"metadata:rate:{self.descriptor.provider_key}",
                rate=f"{rpm}/m",
                burst=1,
                timeout=max(interval * 2, 5.0),
            )
        except Exception:  # noqa: BLE001 - Redis 初始化失败时退回进程内间隔
            with self._lock:
                wait = max(0.0, self._last_call + interval - time.monotonic())
                self._last_call = time.monotonic() + wait
            if wait > 0:
                time.sleep(wait)
            return
        if not acquired:
            raise ProviderRateLimited(self.descriptor.provider_key, "provider 限流等待超时")

    def record_success(self) -> None:
        with self._lock:
            self._success += 1
            self._failures = 0
            self._open_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._failure += 1
            self._failures += 1
            if self._failures >= self.descriptor.circuit_failures:
                self._open_until = time.monotonic() + self.descriptor.circuit_cooldown_seconds

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "provider": self.descriptor.provider_key,
                "open": time.monotonic() < self._open_until,
                "failures": self._failure,
                "success": self._success,
                "open_until_seconds": max(0, int(self._open_until - time.monotonic())),
            }


class ProviderRuntimeRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runtimes: dict[str, ProviderRuntime] = {}

    def get(self, descriptor: ProviderDescriptor) -> ProviderRuntime:
        with self._lock:
            runtime = self._runtimes.get(descriptor.provider_key)
            if runtime is None or runtime.descriptor != descriptor:
                runtime = ProviderRuntime(descriptor=descriptor)
                self._runtimes[descriptor.provider_key] = runtime
            return runtime

    def snapshot(self) -> list[dict]:
        with self._lock:
            runtimes = list(self._runtimes.values())
        return [runtime.snapshot() for runtime in runtimes]
