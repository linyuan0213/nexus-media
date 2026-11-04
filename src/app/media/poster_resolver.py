"""订阅/下载海报选择：优先插件元数据源并验证可访问性."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

import log
from app.infrastructure.image_proxy.referer_registry import image_referer_registry
from app.media.metadata import ProviderRef
from app.media.metadata.registry import registry as metadata_registry


def resolve_provider_poster(provider: str, external_id: str, media_type: Any) -> str:
    obj = metadata_registry.get_provider(provider)
    detail = getattr(obj, "detail", None)
    if obj is None or not callable(detail):
        return ""
    try:
        record = detail(ProviderRef(provider=provider, external_id=external_id, media_type=media_type), None)
    except Exception:  # noqa: BLE001
        return ""
    posters = (getattr(record, "images", None) or {}).get("poster") or [] if record is not None else []
    return str(getattr(posters[0], "url", "") or "") if posters else ""


def preferred_profile_poster(
    image: str,
    content_profile: str | None,
    provider: str | None,
    external_id: str | None,
    media_type: Any,
) -> str:
    """自定义画像优先使用插件优先级海报，并拒绝不可访问的图片 URL。"""
    if not image or not content_profile or content_profile == "default":
        return image
    if provider and external_id:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(resolve_provider_poster, provider, external_id, media_type)
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
