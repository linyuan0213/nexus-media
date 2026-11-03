"""索引器 provider 站点目录，供站点管理和资源页复用。"""

from __future__ import annotations

import log

from .global_registry import get_global_registry


def external_indexer_sites() -> list[dict]:
    result: list[dict] = []
    for provider in get_global_registry().list():
        try:
            info = provider.info()
        except Exception as exc:  # noqa: BLE001
            log.warn(f"[Indexer]读取 provider 站点失败 {provider.provider_id}: {exc}")
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
