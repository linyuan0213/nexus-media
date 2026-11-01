"""通用展示图片转换器：插件可按内容画像改写页面展示图片.

只作用于探索、下载、历史、订阅等页面；通知图片走 message_image_policy。
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from urllib.parse import parse_qs, unquote, urlsplit

_TRANSFORMERS: list[Callable[[str, str], str]] = []


def register_display_image_transformer(
    transformer: Callable[[str, str], str],
) -> None:
    if transformer not in _TRANSFORMERS:
        _TRANSFORMERS.append(transformer)


def unregister_display_image_transformer(transformer: Callable[[str, str], str]) -> None:
    with contextlib.suppress(ValueError):
        _TRANSFORMERS.remove(transformer)


def clear_display_image_transformers() -> None:
    _TRANSFORMERS.clear()


def transform_display_image(content_profile: str, image_url: str) -> str:
    """按注册顺序转换展示图片；先还原历史遗留的模糊代理 URL."""
    value = str(image_url or "")
    for _ in range(5):
        unwrapped = unwrap_display_image_url(value)
        if unwrapped == value:
            break
        value = unwrapped
    profile = str(content_profile or "")
    for transformer in list(_TRANSFORMERS):
        try:
            transformed = transformer(profile, value)
            if transformed:
                value = transformed
        except Exception:  # noqa: BLE001 - 单插件失败不影响图片展示
            continue
    return value


def unwrap_display_image_url(image_url: str | None) -> str:
    """把展示代理 URL 还原成原始图片 URL，避免写回数据库或被下载器当成本地路径."""
    value = str(image_url or "")
    for _ in range(5):
        try:
            parts = urlsplit(value)
            if parts.path.rstrip("/").endswith(("/img/blur", "/img/crop")):
                raw = (parse_qs(parts.query).get("url") or [""])[0]
                if not raw:
                    break
                value = unquote(raw)
                continue
            if parts.path == "/img" and parts.query.startswith("url="):
                raw = (parse_qs(parts.query).get("url") or [""])[0]
                if not raw:
                    break
                value = unquote(raw)
                continue
            if parts.path.startswith("/img/library/"):
                value = unquote(parts.path[len("/img/library/") :])
                continue
        except Exception:
            break
        break
    return value
