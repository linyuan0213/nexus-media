"""别名筛选：只保留中文、英文、以及非中文发行国家的本土标题."""

from __future__ import annotations

import re

_MAX_ALIASES = 3
_LATIN_RE = re.compile(r"[A-Za-z]{3,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CHINESE_COUNTRIES = {"CN", "TW", "HK", "MO", "SG"}
_CHINESE_LANGUAGES = {"zh", "cn", "zh-cn", "zh-tw", "zh-hk", "zh-hant", "zh-hans"}


def _is_chinese_native(countries: list[str] | None, original_language: str | None) -> bool:
    country_values = {str(item).upper() for item in (countries or []) if item}
    language = str(original_language or "").strip().lower()
    return bool(country_values & _CHINESE_COUNTRIES) or language in _CHINESE_LANGUAGES


def select_aliases(
    title: str | None,
    original_title: str | None,
    aliases: list[str] | tuple[str, ...] | None,
    *,
    countries: list[str] | None = None,
    original_language: str | None = None,
) -> list[str]:
    """中文标题 + 非中文发行国家的本土标题 + 英文别名，最多 3 个.

    中国发行作品的本土语言就是中文，不再额外保留一条“本土标题”。
    """
    values = list(aliases or [])
    result: list[str] = []
    seen: set[str] = set()

    def add(value: str | None) -> None:
        text = str(value or "").strip()
        if not text:
            return
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            result.append(text)

    add(title)
    if not _is_chinese_native(countries, original_language):
        add(original_title)
    for value in values:
        if _LATIN_RE.search(str(value or "")):
            add(value)
            break
    if len(result) < _MAX_ALIASES and not any(_LATIN_RE.search(item) for item in result):
        # 没有英文别名时，若英文原名存在则补上。
        add(original_title)
    return result[:_MAX_ALIASES]
