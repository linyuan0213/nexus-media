"""分类映射表加载与字段归一化."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import log


def _taxonomy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "category" / "taxonomy.json"


@dataclass(frozen=True)
class Taxonomy:
    genre_aliases: dict[str, str]
    genre_id_keys: dict[int, set[str]]
    language_aliases: dict[str, str]
    country_aliases: dict[str, str]

    @property
    def available(self) -> bool:
        return bool(self.genre_aliases or self.genre_id_keys)

    def genre_keys(self, value: Any, media_type: str | None = None) -> set[str]:
        """把 ID、名称或 {id,name} 归一化为内部 genre key."""
        result: set[str] = set()
        if value is None:
            return result
        if isinstance(value, dict):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            values = [value]
        for item in values:
            if isinstance(item, dict):
                raw_id = item.get("id")
                raw_name = item.get("name")
                if raw_id is not None:
                    result.update(self._genre_id(str(raw_id), media_type))
                if raw_name:
                    result.update(self._genre_name(str(raw_name)))
            elif isinstance(item, (int, float)) or str(item).strip().isdigit():
                result.update(self._genre_id(str(item), media_type))
            else:
                result.update(self._genre_name(str(item)))
        return result

    def _genre_id(self, value: str, media_type: str | None) -> set[str]:
        number = int(value) if value.isdigit() else None
        if number is None:
            return set()
        return set(self.genre_id_keys.get(number, set()))

    def _genre_name(self, value: str) -> set[str]:
        key = self.genre_aliases.get(value.strip().lower())
        return {key} if key else set()

    def language_codes(self, value: Any) -> set[str]:
        result: set[str] = set()
        for item in _as_values(value):
            code = self.language_aliases.get(str(item).strip().lower())
            if code:
                result.add(code)
        return result

    def country_codes(self, value: Any) -> set[str]:
        result: set[str] = set()
        for item in _as_values(value):
            if isinstance(item, dict):
                item = item.get("iso_3166_1") or item.get("name") or ""
            code = self.country_aliases.get(str(item).strip().lower())
            if code:
                result.add(code)
        return result


def _as_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


@lru_cache(maxsize=1)
def load_taxonomy() -> Taxonomy:
    path = _taxonomy_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warn(f"[CategoryTaxonomy]加载失败，分类归一化退化为原值: {exc}")
        return Taxonomy({}, {}, {}, {})

    genre_aliases: dict[str, str] = {}
    genre_id_keys: dict[int, set[str]] = {}
    for key, item in (data.get("genres") or {}).items():
        for alias in [*((item or {}).get("aliases") or []), *((item or {}).get("labels") or {}).values()]:
            text = str(alias or "").strip()
            if text:
                genre_aliases[text.lower()] = key
        for ids in ((item or {}).get("tmdb") or {}).values():
            for raw_id in ids or []:
                if str(raw_id).isdigit():
                    genre_id_keys.setdefault(int(raw_id), set()).add(key)

    language_aliases: dict[str, str] = {}
    for key, item in (data.get("languages") or {}).items():
        for alias in [*((item or {}).get("aliases") or []), *((item or {}).get("labels") or {}).values()]:
            text = str(alias or "").strip()
            if text:
                language_aliases[text.lower()] = key

    country_aliases: dict[str, str] = {}
    for key, item in (data.get("countries") or {}).items():
        for alias in [*((item or {}).get("aliases") or []), *((item or {}).get("labels") or {}).values()]:
            text = str(alias or "").strip()
            if text:
                country_aliases[text.lower()] = str(key).upper()

    return Taxonomy(genre_aliases, genre_id_keys, language_aliases, country_aliases)
