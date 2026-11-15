"""发现（探索页）来源适配器与季度工具."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Literal

from ..models import (
    DiscoveryItem,
    FacetValue,
)

FeedKind = Literal["ranking", "trending", "latest", "calendar", "seasonal", "collection", "search"]


def season_range(season: str | None, *, today: date | None = None) -> tuple[str, str]:
    """把 2026-winter / 2026-q1 转为日期区间；缺省为当前季度."""
    current = today or date.today()
    year = current.year
    key = (season or "").strip().lower()
    if "-" in key:
        raw_year, raw_key = key.split("-", 1)
        if raw_year.isdigit():
            year = int(raw_year)
            key = raw_key
    mapping = {
        "winter": (1, 1, 3, 31),
        "spring": (4, 1, 6, 30),
        "summer": (7, 1, 9, 30),
        "fall": (10, 1, 12, 31),
        "autumn": (10, 1, 12, 31),
        "q1": (1, 1, 3, 31),
        "q2": (4, 1, 6, 30),
        "q3": (7, 1, 9, 30),
        "q4": (10, 1, 12, 31),
    }
    if key not in mapping:
        month = current.month
        key = "q1" if month <= 3 else "q2" if month <= 6 else "q3" if month <= 9 else "q4"
    start_month, start_day, end_month, end_day = mapping[key]
    return (
        date(year, start_month, start_day).isoformat(),
        date(year, end_month, end_day).isoformat(),
    )


def current_season(today: date | None = None) -> str:
    current = today or date.today()
    quarter = (current.month - 1) // 3 + 1
    return f"{current.year}-q{quarter}"


_NON_GENRE_TAGS = {
    "日本",
    "中国",
    "美国",
    "韩国",
    "欧美",
    "TV",
    "TVA",
    "WEB",
    "OVA",
    "剧场版",
    "动画",
    "日本动画",
    "漫画",
    "小说",
    "游戏",
    "原创",
    "续作",
    "未定档",
    "季番",
    "漫改",
    "轻改",
    "小说改",
    "漫画改",
    "游戏改",
    "轻小说改",
}


_COUNTRY_LABELS = (
    "日本",
    "中国香港",
    "中国台湾",
    "中国",
    "美国",
    "韩国",
    "英国",
    "法国",
    "泰国",
    "欧美",
)


_LANGUAGE_COUNTRY_LABELS = {
    "ja": "日本",
    "zh": "中国",
    "ko": "韩国",
    "en": "美国",
    "th": "泰国",
    "fr": "法国",
    "de": "德国",
    "es": "西班牙",
}

_COUNTRY_CODE_LABELS = {
    "JP": "日本",
    "CN": "中国",
    "HK": "中国香港",
    "TW": "中国台湾",
    "US": "美国",
    "KR": "韩国",
    "GB": "英国",
    "FR": "法国",
    "TH": "泰国",
}


def _country_from_values(values: list[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        mapped = _COUNTRY_CODE_LABELS.get(text.upper())
        if mapped and mapped not in result:
            result.append(mapped)
            continue
        for country in _COUNTRY_LABELS:
            if country in text and country not in result:
                result.append(country)
    return result


_COUNTRY_FILTER_OPTIONS = (
    "中国",
    "中国香港",
    "中国台湾",
    "日本",
    "韩国",
    "美国",
    "英国",
    "法国",
    "德国",
    "泰国",
)


def _country_options() -> list[FacetValue]:
    """固定常规国家/地区，避免国家选项随当前页数据漂移."""
    return [FacetValue(value=country, label=country) for country in _COUNTRY_FILTER_OPTIONS]


def _country_facets(items: list[DiscoveryItem]) -> list[FacetValue]:
    counts = Counter(country for item in items for country in item.countries)
    return [
        FacetValue(value=country, label=country, count=count)
        for country, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _country_filter(items: list[DiscoveryItem], country: str) -> list[DiscoveryItem]:
    if not country:
        return items
    return [item for item in items if country in item.countries or any(country in str(tag) for tag in item.tags)]


def _genre_facets(items: list[DiscoveryItem], limit: int = 16) -> tuple[list[str], list[FacetValue]]:
    """从当前页标签动态提取主流题材，其余归入其他."""
    counts = Counter(
        str(tag).strip()
        for item in items
        for tag in item.tags
        if str(tag).strip()
        and str(tag).strip() not in _NON_GENRE_TAGS
        and not any(char.isdigit() for char in str(tag))
        and not str(tag).isascii()
        and len(str(tag)) <= 6
    )
    mainstream = [tag for tag, _count in counts.most_common(limit)]
    tagged = 0
    for item in items:
        if any(any(main in tag for tag in item.tags) for main in mainstream):
            tagged += 1
    facets = [
        FacetValue(
            value=tag,
            label=tag,
            count=sum(1 for item in items if any(tag in value for value in item.tags)),
        )
        for tag in mainstream
    ]
    if tagged < len(items):
        facets.append(FacetValue(value="其他", label="其他", count=len(items) - tagged))
    return mainstream, facets
