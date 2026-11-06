"""订阅/下载海报选择：优先插件元数据源并验证可访问性."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

import log
from app.infrastructure.image_proxy.referer_registry import image_referer_registry
from app.media.metadata.gateway import MetadataContext, MetadataGateway


def resolve_provider_poster(
    provider: str,
    external_id: str,
    media_type: Any,
    metadata_gateway: MetadataGateway | None = None,
) -> str:
    if metadata_gateway is None:
        return ""
    try:
        record = metadata_gateway.lookup(
            provider,
            external_id,
            context=MetadataContext(purpose="poster", allow_private=True),
            media_type=media_type,
        )
    except Exception:  # noqa: BLE001
        return ""
    images = (record or {}).get("images") if isinstance(record, dict) else {}
    posters = (images or {}).get("poster") or []
    return str((posters[0] or {}).get("url") or "") if posters and isinstance(posters[0], dict) else ""


def preferred_profile_poster(
    image: str,
    content_profile: str | None,
    provider: str | None,
    external_id: str | None,
    media_type: Any,
    metadata_gateway: MetadataGateway | None = None,
) -> str:
    """自定义画像优先使用插件优先级海报，并拒绝不可访问的图片 URL。"""
    if not image or not content_profile or content_profile == "default":
        return image
    if provider and external_id:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(resolve_provider_poster, provider, external_id, media_type, metadata_gateway)
        try:
            poster = future.result(timeout=3)
        except Exception:  # noqa: BLE001 - 超时回退原图
            poster = ""
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if poster:
            return poster
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        referer = image_referer_registry.resolve(image)
        if referer:
            headers["Referer"] = referer
        with httpx.Client(timeout=2.5, follow_redirects=True) as client:
            if client.get(image, headers=headers).status_code < 400:
                return image
    except Exception as exc:  # noqa: BLE001
        log.debug(f"[Poster]海报可访问性检查失败: {exc}")
    return ""
