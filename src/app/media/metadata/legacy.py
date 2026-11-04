"""旧 ID（TMDBID / DB: / BG:）到 ProviderRef 的解析."""

from __future__ import annotations

from app.domain.mediatypes import MediaType

from .models import ProviderRef
from .refs import parse_media_ref


def parse_legacy_ref(raw_id: str | None, media_type: MediaType) -> ProviderRef | None:
    """解析旧字段；纯数字按 TMDB 处理，未知格式返回 None."""
    if raw_id is None:
        return None
    value = str(raw_id).strip()
    if not value or value in {"0", "None", "null", "NULL"}:
        return None

    # content_id 是内部伪 provider 锚点，必须优先于插件的 ref_prefix 解析，
    # 否则插件误声明 CONTENT_ID 时会被归到 tmdb 等真实 provider。
    if value.upper().startswith("CONTENT_ID:"):
        external_id = value.split(":", 1)[1].strip()
        if external_id:
            return ProviderRef(provider="content_id", external_id=external_id, media_type=media_type)

    parsed = parse_media_ref(value)
    if parsed is None:
        # 兼容未注册内置 provider 的测试/极简启动；正常运行时优先走 descriptor。
        if value.isdigit():
            parsed = ("tmdb", value)
        elif ":" in value:
            prefix, external = value.split(":", 1)
            provider = {
                "TMDB": "tmdb",
                "DOUBAN": "douban",
                "DB": "douban",
                "BANGUMI": "bangumi",
                "BGM": "bangumi",
                "BG": "bangumi",
                "CONTENT_ID": "content_id",
            }.get(prefix.upper())
            if provider and external:
                parsed = (provider, external)
    if parsed is None:
        return None
    provider, external_id = parsed
    return ProviderRef(provider=provider, external_id=external_id, media_type=media_type)
