"""索引器 provider 站点目录，供站点管理和资源页复用。"""

from __future__ import annotations

import threading
import time

import log

from .global_registry import get_global_registry
from .models import IndexerInfo

_CACHE_TTL = 10.0
_info_cache: dict[str, tuple[float, IndexerInfo]] = {}
_cache_lock = threading.RLock()


def _provider_info(provider) -> IndexerInfo | None:
    now = time.monotonic()
    with _cache_lock:
        cached = _info_cache.get(provider.provider_id)
        if cached is not None and now - cached[0] < _CACHE_TTL:
            return cached[1]
    try:
        info = provider.info()
    except Exception as exc:  # noqa: BLE001
        log.warn(f"[Indexer]读取 provider 站点失败 {provider.provider_id}: {exc}")
        with _cache_lock:
            cached = _info_cache.get(provider.provider_id)
        return cached[1] if cached is not None else None
    with _cache_lock:
        _info_cache[provider.provider_id] = (now, info)
    return info


def external_indexer_sites() -> list[dict]:
    result: list[dict] = []
    for provider in get_global_registry().list():
        info = _provider_info(provider)
        if info is None:
            continue
        for site in info.sites:
            result.append(
                {
                    "id": f"provider:{info.provider_id}:{site.id}",
                    "name": site.id,
                    "display_name": site.name,
                    "url": "",
                    "source": info.provider_id,
                    "source_label": info.name,
                    "source_icon": info.icon,
                    "third_party": True,
                    "enabled": True,
                    "public": site.public,
                    "site_public": site.public,
                    "has_rss": False,
                    "rss_enable": False,
                    "brush_enable": False,
                    "parse": False,
                }
            )
    return result
