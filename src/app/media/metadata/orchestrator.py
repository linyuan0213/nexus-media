"""元数据编排器.

负责按引用并行取数、收集能力声明、交给合成器；不实现具体 provider。
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.media_types import ProviderMediaType

from .composer import MetadataComposer
from .errors import (
    ProviderError,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from .metrics import record_event, record_provider_result
from .models import (
    FieldValue,
    MediaMetadata,
    ProviderCapability,
    ProviderRecord,
    ProviderRef,
    SourceTier,
)
from .policy import MetadataPolicy
from .registry import MetadataRegistry
from .runtime import ProviderContext, ProviderRuntimeRegistry


@dataclass
class ComposeResult:
    metadata: MediaMetadata | None = None
    records: list[ProviderRecord] = field(default_factory=list)
    errors: list[ProviderError] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return bool(self.errors)


class MetadataOrchestrator:
    """并行取数 + 合成."""

    def __init__(
        self,
        registry: MetadataRegistry,
        *,
        composer: MetadataComposer | None = None,
        max_workers: int = 4,
        cache_ttl_seconds: int = 1800,
    ) -> None:
        self._registry = registry
        self._composer = composer or MetadataComposer()
        self._max_workers = max(1, max_workers)
        self._cache_ttl = max(0, cache_ttl_seconds)
        self._cache: dict[tuple[str, str, str, int, int], tuple[datetime, ProviderRecord]] = {}
        self._cache_lock = threading.Lock()
        self._runtimes = ProviderRuntimeRegistry()

    def compose(
        self,
        identity_id: str,
        refs: list[ProviderRef],
        policy: MetadataPolicy,
        *,
        media_type: ProviderMediaType | None = None,
        content_profile: str = "default",
        scope: str = "default",
        locked: dict[str, FieldValue] | None = None,
    ) -> ComposeResult:
        records, errors, capabilities = self._fetch(refs)
        if not records:
            return ComposeResult(metadata=None, records=[], errors=errors)
        if not policy.allow_partial and policy.primary not in {record.provider for record in records}:
            errors.append(ProviderUnavailable(policy.primary, "主源无可用记录且策略不允许部分结果"))
            return ComposeResult(metadata=None, records=records, errors=errors)

        metadata = self._composer.compose(
            identity_id,
            records,
            policy,
            content_profile=content_profile,
            scope=scope,
            media_type=media_type,
            capabilities=capabilities,
            locked=locked,
        )
        return ComposeResult(metadata=metadata, records=records, errors=errors)

    def _fetch(
        self,
        refs: list[ProviderRef],
    ) -> tuple[list[ProviderRecord], list[ProviderError], dict[str, set[ProviderCapability | str]]]:
        records: list[ProviderRecord] = []
        errors: list[ProviderError] = []
        capabilities: dict[str, set[ProviderCapability | str]] = {}

        jobs = []
        runtimes = {}
        seen_refs: set[tuple[str, str, str]] = set()
        for ref in refs:
            ref_key = (ref.provider, ref.external_id, ref.scope)
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)
            provider = self._registry.get_provider(ref.provider)
            if provider is None:
                errors.append(ProviderUnavailable(ref.provider, "provider 未注册"))
                continue
            cached = self._cache_get(
                (
                    *ref_key,
                    provider.descriptor.result_schema_version,
                    self._registry.revision,
                )
            )
            if cached is not None:
                cached.source_tier = cached.source_tier or _tier_of(provider)
                records.append(cached)
                capabilities.setdefault(ref.provider, set(provider.descriptor.capabilities))
                continue
            runtime = self._runtimes.get(provider.descriptor)
            try:
                runtime.acquire()
            except ProviderError as exc:
                errors.append(exc)
                continue
            capabilities[ref.provider] = set(provider.descriptor.capabilities)
            runtimes[(ref.provider, ref.external_id, ref.scope)] = runtime
            jobs.append(
                (
                    provider,
                    ref,
                    ProviderContext(
                        provider.descriptor,
                        runtime,
                        cache=runtime.cache,
                    ),
                )
            )

        if not jobs:
            return records, errors, capabilities

        executor = ThreadPoolExecutor(max_workers=min(self._max_workers, len(jobs)))
        future_map = {executor.submit(provider.detail, ref, ctx): (ref, provider) for provider, ref, ctx in jobs}
        deadline = max(
            (provider.descriptor.timeout_seconds for provider, _, _ in jobs),
            default=30,
        )
        try:
            try:
                completed = as_completed(future_map, timeout=max(1, deadline))
                for future in completed:
                    ref, provider = future_map[future]
                    runtime = runtimes[(ref.provider, ref.external_id, ref.scope)]
                    started = time.monotonic()
                    try:
                        record = future.result()
                    except ProviderError as exc:
                        runtime.record_failure()
                        record_provider_result(
                            ref.provider,
                            ok=False,
                            latency_ms=int((time.monotonic() - started) * 1000),
                        )
                        record_event(
                            "metadata.provider.failed",
                            provider=ref.provider,
                            error=type(exc).__name__,
                        )
                        errors.append(exc)
                        continue
                    except Exception as exc:  # noqa: BLE001 - 隔离第三方 provider
                        runtime.record_failure()
                        record_provider_result(
                            ref.provider,
                            ok=False,
                            latency_ms=int((time.monotonic() - started) * 1000),
                        )
                        errors.append(ProviderSchemaError(ref.provider, f"provider 返回异常: {exc}"))
                        continue
                    runtime.record_success()
                    record_provider_result(
                        ref.provider,
                        ok=True,
                        latency_ms=int((time.monotonic() - started) * 1000),
                    )
                    if record is not None:
                        record.source_tier = record.source_tier or _tier_of(provider)
                        records.append(record)
                        self._cache_put(
                            (
                                ref.provider,
                                ref.external_id,
                                ref.scope,
                                provider.descriptor.result_schema_version,
                                self._registry.revision,
                            ),
                            record,
                        )
            except TimeoutError:
                for future, (ref, _provider) in future_map.items():
                    if future.done():
                        continue
                    runtime = runtimes[(ref.provider, ref.external_id, ref.scope)]
                    runtime.record_failure()
                    record_provider_result(ref.provider, ok=False, latency_ms=deadline * 1000)
                    errors.append(
                        ProviderTimeout(
                            ref.provider,
                            f"provider 超时（{deadline}s）",
                        )
                    )
                    future.cancel()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        return records, errors, capabilities

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def runtime_for(self, descriptor):
        return self._runtimes.get(descriptor)

    def runtime_snapshot(self) -> list[dict]:
        return self._runtimes.snapshot()

    def _cache_get(self, key: tuple[str, str, str, int, int]) -> ProviderRecord | None:
        if not self._cache_ttl:
            return None
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            created, record = entry
            if datetime.now() - created > timedelta(seconds=self._cache_ttl):
                self._cache.pop(key, None)
                return None
            return record

    def _cache_put(self, key: tuple[str, str, str, int, int], record: ProviderRecord) -> None:
        if not self._cache_ttl:
            return
        with self._cache_lock:
            self._cache[key] = (datetime.now(), record)


def _tier_rank(tier: SourceTier | None) -> int:
    return {"api": 0, "html": 1, "scraping": 2}.get(str(tier or ""), 9)


def _tier_of(provider: object) -> SourceTier | None:
    descriptor = getattr(provider, "descriptor", None)
    tiers = getattr(descriptor, "source_tiers", None) if descriptor else None
    if not tiers:
        return None
    return min(tiers, key=_tier_rank)
