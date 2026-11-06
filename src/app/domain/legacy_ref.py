"""旧媒体 ID 到 provider 引用的纯解析.

只处理历史字段（TMDBID / DB: / BG: 等）的兼容映射，不依赖 provider 注册表，
供仓储层与 domain 复用；需要按插件声明格式解析时使用 media.metadata.refs。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.mediatypes import MediaType

_PREFIX_ALIASES = {
    "TMDB": "tmdb",
    "DOUBAN": "douban",
    "DB": "douban",
    "BANGUMI": "bangumi",
    "BGM": "bangumi",
    "BG": "bangumi",
    "CONTENT_ID": "content_id",
}


@dataclass(frozen=True)
class LegacyProviderRef:
    provider: str
    external_id: str
    media_type: MediaType


def parse_legacy_ref(raw_id: str | None, media_type: MediaType) -> LegacyProviderRef | None:
    """解析历史字段；纯数字按 TMDB 处理，未知格式返回 None."""
    if raw_id is None:
        return None
    value = str(raw_id).strip()
    if not value or value in {"0", "None", "null", "NULL"}:
        return None

    if ":" in value:
        prefix, external = value.split(":", 1)
        external = external.strip()
        if not prefix.strip() or not external:
            return None
        provider = _PREFIX_ALIASES.get(prefix.strip().upper())
        if provider is None:
            # 统一身份约定为 provider:external；未在内置别名中的前缀按 provider key 处理。
            provider = prefix.strip().lower()
        return LegacyProviderRef(provider=provider, external_id=external, media_type=media_type)

    if value.isdigit():
        return LegacyProviderRef(provider="tmdb", external_id=value, media_type=media_type)
    return None
