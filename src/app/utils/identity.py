"""媒体身份兜底工具."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_IDENTITY_CODE_RE = re.compile(r"([A-Za-z]{2,12})[-_ ]?(\d{2,6})")


def fallback_identity(
    title: Any,
    media_type: str = "movie",
    season: int = 0,
    anchor_provider: str = "",
    anchor_external_id: str = "",
) -> str:
    """为缺失 anchor 的记录生成稳定身份；长度适配 IDENTITY_ID varchar(26)."""

    def fit(value: str) -> str:
        if len(value) <= 26:
            return value
        return "local:" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]

    provider = str(anchor_provider or "").strip()
    external_id = str(anchor_external_id or "").strip()
    if provider and external_id:
        return fit(f"{provider}:{external_id}")
    text = str(title or "").strip()
    match = _IDENTITY_CODE_RE.search(text)
    if match:
        code = f"{match.group(1).upper()}-{match.group(2)}"
        suffix = ""
        if media_type != "movie" or season:
            suffix = f":{media_type}:{int(season or 0)}"
        return fit(f"local:{code}{suffix}")
    digest = hashlib.sha1(f"{text}|{media_type}|{int(season or 0)}".encode("utf-8")).hexdigest()[:20]
    return f"local:{digest}"
