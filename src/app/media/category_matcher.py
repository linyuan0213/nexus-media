"""分类匹配：统一 TMDB/豆瓣/Bangumi 字段，并兼容旧 TMDB 规则."""

from __future__ import annotations

from typing import Any

from .category_context import CategoryContext
from .category_taxonomy import Taxonomy, load_taxonomy

_FIELD_MAP = {
    "genres": "genres",
    "genre": "genres",
    "genre_ids": "genres",
    "original_language": "languages",
    "language": "languages",
    "spoken_languages": "languages",
    "languages": "languages",
    "origin_country": "countries",
    "production_countries": "countries",
    "countries": "countries",
    "country": "countries",
    "tags": "tags",
    "tag": "tags",
    "content_profile": "content_profiles",
    "content_profiles": "content_profiles",
    "providers": "providers",
    "provider": "providers",
    "prefix": "prefix",
    "flags": "flags",
}


def _split_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _normalize_expected(field: str, value: Any, taxonomy: Taxonomy) -> set[str]:
    values = _split_values(value)
    if field == "genres":
        result = taxonomy.genre_keys(values)
        if not result:
            result = {str(item).strip().lower() for item in values if str(item).strip()}
        return result
    if field == "languages":
        result = taxonomy.language_codes(values)
        if not result:
            result = {str(item).strip().lower() for item in values if str(item).strip()}
        return result
    if field == "countries":
        result = taxonomy.country_codes(values)
        if not result:
            result = {str(item).strip().upper() for item in values if str(item).strip()}
        return result
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _context_values(context: CategoryContext, field: str) -> set[str]:
    if field == "genres":
        return {item.lower() for item in context.genres}
    if field == "languages":
        return {item.lower() for item in context.languages}
    if field == "countries":
        return {item.upper() for item in context.countries}
    if field == "tags":
        return context.tags
    if field == "content_profiles":
        return context.content_profiles
    if field == "providers":
        return context.providers
    if field == "prefix":
        return {context.prefix.lower()} if context.prefix else set()
    if field == "flags":
        return context.flags
    return set()


def _matches_legacy_rules(
    rules: dict[str, Any],
    context: CategoryContext,
    taxonomy: Taxonomy,
) -> bool:
    for raw_field, raw_value in rules.items():
        if raw_value in (None, ""):
            continue
        field = _FIELD_MAP.get(str(raw_field), str(raw_field))
        expected = _normalize_expected(field, raw_value, taxonomy)
        actual = _context_values(context, field)
        if not expected or not actual or not (expected & actual):
            return False
    return True


def _legacy_get_category(categorys, tmdb_info):
    """旧实现，仅在 taxonomy 不可用时兜底."""
    if not tmdb_info or not categorys:
        return ""
    fallback = ""
    for key, item in categorys.items():
        if not item:
            if not fallback:
                fallback = key
            continue
        match_flag = True
        for attr, value in item.items():
            if not value:
                continue
            info_value = tmdb_info.get(attr)
            if not info_value:
                match_flag = False
                continue
            if attr == "production_countries":
                info_values = [str(val.get("iso_3166_1")).upper() for val in info_value]
            elif isinstance(info_value, list):
                info_values = [str(val).upper() for val in info_value]
            else:
                info_values = [str(info_value).upper()]
            values = [str(val).upper() for val in str(value).split(",")] if "," in str(value) else [str(value).upper()]
            if not set(values).intersection(set(info_values)):
                match_flag = False
        if match_flag:
            return key
    return fallback


def get_category(categorys, tmdb_info, media_type: str | None = None):
    """按分类配置匹配，规则先经过 taxonomy 归一化."""
    if not tmdb_info or not categorys:
        return ""
    taxonomy = load_taxonomy()
    if not taxonomy.available:
        return _legacy_get_category(categorys, tmdb_info)
    context = CategoryContext.from_info(tmdb_info, media_type=media_type)
    fallback = ""
    for key, rules in categorys.items():
        if not rules:
            if not fallback:
                fallback = key
            continue
        if _matches_legacy_rules(rules, context, taxonomy):
            return key
    return fallback


def match_category(categorys, context: CategoryContext) -> str:
    """基于已建立的上下文匹配分类，供后续多源合成调用."""
    taxonomy = load_taxonomy()
    fallback = ""
    for key, rules in (categorys or {}).items():
        if not rules:
            if not fallback:
                fallback = key
            continue
        if _matches_legacy_rules(rules, context, taxonomy):
            return key
    return fallback
