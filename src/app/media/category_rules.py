"""分类规则 DSL：兼容旧字段等值规则，并支持来源/操作符."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .category_context import CategoryContext
from .category_taxonomy import load_taxonomy

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


@dataclass(frozen=True)
class CategoryRule:
    field: str
    operator: str
    value: Any
    source: str | None = None

    @classmethod
    def from_mapping(cls, item: dict[str, Any]) -> CategoryRule | None:
        field = str(item.get("field") or "").strip()
        operator = str(item.get("operator") or "eq").strip().lower()
        if not field:
            return None
        return cls(field=field, operator=operator, value=item.get("value"), source=item.get("source") or None)

    def matches(self, context: CategoryContext) -> bool:
        field = _FIELD_MAP.get(self.field, self.field)
        if self.source and field in context.provenance:
            if self.source not in context.provenance[field]:
                return False
        actual = _context_values(context, field)
        expected = _expected_values(self.field, self.value)
        if self.operator == "exists":
            return bool(actual)
        if self.operator == "eq":
            return bool(actual & expected)
        if self.operator == "neq":
            return not bool(actual & expected)
        if self.operator == "in":
            return bool(actual & expected)
        if self.operator == "not_in":
            return not bool(actual & expected)
        if self.operator == "contains":
            return any(item in value for value in actual for item in expected)
        if self.operator == "contains_any":
            return bool(actual & expected)
        if self.operator == "startswith_any":
            return any(value.startswith(item) for value in actual for item in expected)
        if self.operator == "regex":
            pattern = str(self.value or "")
            try:
                return any(re.search(pattern, value, re.I) for value in actual)
            except re.error:
                return False
        return False


def match_rule_group(
    rules: list[dict[str, Any]] | list[CategoryRule],
    context: CategoryContext,
    mode: str = "all",
) -> bool:
    parsed = [rule if isinstance(rule, CategoryRule) else CategoryRule.from_mapping(rule) for rule in rules]
    conditions = [rule for rule in parsed if rule is not None]
    if not conditions:
        return False
    results = [rule.matches(context) for rule in conditions]
    return any(results) if str(mode).lower() == "any" else all(results)


def _expected_values(field: str, value: Any) -> set[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    taxonomy = load_taxonomy()
    if _FIELD_MAP.get(field, field) == "genres":
        return taxonomy.genre_keys(values) or {str(item).strip().lower() for item in values if str(item).strip()}
    if _FIELD_MAP.get(field, field) == "languages":
        return taxonomy.language_codes(values) or {str(item).strip().lower() for item in values if str(item).strip()}
    if _FIELD_MAP.get(field, field) == "countries":
        return taxonomy.country_codes(values) or {str(item).strip().upper() for item in values if str(item).strip()}
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
