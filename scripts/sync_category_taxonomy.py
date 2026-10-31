"""一次性同步分类映射表并生成 taxonomy.json.

默认离线使用内置映射；提供 TMDB key 时会补齐 TMDB genre id/名称。
豆瓣标签页抓取仅用于补充中文别名，不做运行时请求。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.settings import settings

DEFAULT_OUTPUT = Path("config/category/taxonomy.json")

GENRE_SEEDS: list[dict[str, Any]] = [
    {"key": "action", "zh": "动作", "en": "Action", "tmdb": {"movie": [28]}, "aliases": ["动作", "動作", "Action"]},
    {
        "key": "adventure",
        "zh": "冒险",
        "en": "Adventure",
        "tmdb": {"movie": [12]},
        "aliases": ["冒险", "冒險", "Adventure"],
    },
    {
        "key": "animation",
        "zh": "动画",
        "en": "Animation",
        "tmdb": {"movie": [16], "tv": [16]},
        "aliases": ["动画", "動畫", "动画片", "卡通", "Anime", "Animation"],
    },
    {
        "key": "comedy",
        "zh": "喜剧",
        "en": "Comedy",
        "tmdb": {"movie": [35], "tv": [35]},
        "aliases": ["喜剧", "喜劇", "Comedy"],
    },
    {"key": "crime", "zh": "犯罪", "en": "Crime", "tmdb": {"movie": [80], "tv": [80]}, "aliases": ["犯罪", "Crime"]},
    {
        "key": "documentary",
        "zh": "纪录片",
        "en": "Documentary",
        "tmdb": {"movie": [99], "tv": [99]},
        "aliases": ["纪录片", "紀錄片", "纪录", "Documentary"],
    },
    {
        "key": "drama",
        "zh": "剧情",
        "en": "Drama",
        "tmdb": {"movie": [18], "tv": [18]},
        "aliases": ["剧情", "劇情", "Drama"],
    },
    {
        "key": "family",
        "zh": "家庭",
        "en": "Family",
        "tmdb": {"movie": [10751], "tv": [10751]},
        "aliases": ["家庭", "Family"],
    },
    {
        "key": "fantasy",
        "zh": "奇幻",
        "en": "Fantasy",
        "tmdb": {"movie": [14], "tv": [14]},
        "aliases": ["奇幻", "Fantasy"],
    },
    {"key": "history", "zh": "历史", "en": "History", "tmdb": {"movie": [36]}, "aliases": ["历史", "歷史", "History"]},
    {"key": "horror", "zh": "恐怖", "en": "Horror", "tmdb": {"movie": [27]}, "aliases": ["恐怖", "Horror"]},
    {"key": "music", "zh": "音乐", "en": "Music", "tmdb": {"movie": [10402]}, "aliases": ["音乐", "音樂", "Music"]},
    {
        "key": "mystery",
        "zh": "悬疑",
        "en": "Mystery",
        "tmdb": {"movie": [9648], "tv": [9648]},
        "aliases": ["悬疑", "懸疑", "推理", "Mystery"],
    },
    {
        "key": "romance",
        "zh": "爱情",
        "en": "Romance",
        "tmdb": {"movie": [10749]},
        "aliases": ["爱情", "愛情", "Romance"],
    },
    {
        "key": "science_fiction",
        "zh": "科幻",
        "en": "Science Fiction",
        "tmdb": {"movie": [878]},
        "aliases": ["科幻", "Science Fiction", "Sci-Fi"],
    },
    {
        "key": "tv_movie",
        "zh": "电视电影",
        "en": "TV Movie",
        "tmdb": {"movie": [10770]},
        "aliases": ["电视电影", "電視電影", "TV Movie"],
    },
    {
        "key": "thriller",
        "zh": "惊悚",
        "en": "Thriller",
        "tmdb": {"movie": [53]},
        "aliases": ["惊悚", "驚悚", "Thriller"],
    },
    {"key": "war", "zh": "战争", "en": "War", "tmdb": {"movie": [10752]}, "aliases": ["战争", "戰爭", "War"]},
    {
        "key": "western",
        "zh": "西部",
        "en": "Western",
        "tmdb": {"movie": [37], "tv": [37]},
        "aliases": ["西部", "Western"],
    },
    {
        "key": "action_adventure",
        "zh": "动作冒险",
        "en": "Action & Adventure",
        "tmdb": {"tv": [10759]},
        "aliases": ["动作冒险", "動作冒險", "Action & Adventure"],
    },
    {
        "key": "kids",
        "zh": "儿童",
        "en": "Kids",
        "tmdb": {"tv": [10762]},
        "aliases": ["儿童", "兒童", "儿童片", "亲子", "Kids"],
    },
    {"key": "news", "zh": "新闻", "en": "News", "tmdb": {"tv": [10763]}, "aliases": ["新闻", "新聞", "News"]},
    {"key": "reality", "zh": "真人秀", "en": "Reality", "tmdb": {"tv": [10764]}, "aliases": ["真人秀", "Reality"]},
    {
        "key": "sci_fi_fantasy",
        "zh": "科幻奇幻",
        "en": "Sci-Fi & Fantasy",
        "tmdb": {"tv": [10765]},
        "aliases": ["科幻奇幻", "科幻奇幻", "Sci-Fi & Fantasy"],
    },
    {"key": "soap", "zh": "肥皂剧", "en": "Soap", "tmdb": {"tv": [10766]}, "aliases": ["肥皂剧", "肥皂劇", "Soap"]},
    {"key": "talk", "zh": "脱口秀", "en": "Talk", "tmdb": {"tv": [10767]}, "aliases": ["脱口秀", "脫口秀", "Talk"]},
    {
        "key": "war_politics",
        "zh": "战争政治",
        "en": "War & Politics",
        "tmdb": {"tv": [10768]},
        "aliases": ["战争政治", "戰爭政治", "War & Politics"],
    },
]

LANGUAGE_SEEDS: dict[str, dict[str, Any]] = {
    "zh": {"zh": "汉语", "en": "Chinese", "aliases": ["汉语", "中文", "華語", "Chinese", "zh", "cn"]},
    "ja": {"zh": "日语", "en": "Japanese", "aliases": ["日语", "日本語", "日語", "Japanese", "ja", "jp"]},
    "ko": {"zh": "韩语", "en": "Korean", "aliases": ["韩语", "韓語", "韓国語", "Korean", "ko", "kr"]},
    "en": {"zh": "英语", "en": "English", "aliases": ["英语", "英語", "English", "en"]},
    "fr": {"zh": "法语", "en": "French", "aliases": ["法语", "法語", "French", "fr"]},
    "de": {"zh": "德语", "en": "German", "aliases": ["德语", "德語", "German", "de"]},
    "es": {"zh": "西班牙语", "en": "Spanish", "aliases": ["西班牙语", "西班牙語", "Spanish", "es"]},
    "it": {"zh": "意大利语", "en": "Italian", "aliases": ["意大利语", "意大利語", "Italian", "it"]},
    "ru": {"zh": "俄语", "en": "Russian", "aliases": ["俄语", "俄語", "Russian", "ru"]},
    "th": {"zh": "泰语", "en": "Thai", "aliases": ["泰语", "泰語", "Thai", "th"]},
    "pt": {"zh": "葡萄牙语", "en": "Portuguese", "aliases": ["葡萄牙语", "葡萄牙語", "Portuguese", "pt"]},
}

COUNTRY_SEEDS: dict[str, dict[str, Any]] = {
    "CN": {"zh": "中国", "en": "China", "aliases": ["中国", "中國", "China", "CN", "CHN"]},
    "HK": {"zh": "中国香港", "en": "Hong Kong", "aliases": ["香港", "中国香港", "Hong Kong", "HK", "HKG"]},
    "TW": {"zh": "中国台湾", "en": "Taiwan", "aliases": ["台湾", "台灣", "Taiwan", "TW", "TWN"]},
    "JP": {"zh": "日本", "en": "Japan", "aliases": ["日本", "Japan", "JP", "JPN"]},
    "KR": {"zh": "韩国", "en": "South Korea", "aliases": ["韩国", "韓國", "South Korea", "KR", "KOR"]},
    "US": {"zh": "美国", "en": "United States", "aliases": ["美国", "美國", "United States", "US", "USA"]},
    "GB": {"zh": "英国", "en": "United Kingdom", "aliases": ["英国", "英國", "United Kingdom", "GB", "UK", "GBR"]},
    "FR": {"zh": "法国", "en": "France", "aliases": ["法国", "法國", "France", "FR", "FRA"]},
    "DE": {"zh": "德国", "en": "Germany", "aliases": ["德国", "德國", "Germany", "DE", "DEU"]},
    "IT": {"zh": "意大利", "en": "Italy", "aliases": ["意大利", "Italy", "IT", "ITA"]},
    "ES": {"zh": "西班牙", "en": "Spain", "aliases": ["西班牙", "Spain", "ES", "ESP"]},
    "RU": {"zh": "俄罗斯", "en": "Russia", "aliases": ["俄罗斯", "俄羅斯", "Russia", "RU", "RUS"]},
    "IN": {"zh": "印度", "en": "India", "aliases": ["印度", "India", "IN", "IND"]},
    "TH": {"zh": "泰国", "en": "Thailand", "aliases": ["泰国", "泰國", "Thailand", "TH", "THA"]},
    "CA": {"zh": "加拿大", "en": "Canada", "aliases": ["加拿大", "Canada", "CA", "CAN"]},
    "AU": {"zh": "澳大利亚", "en": "Australia", "aliases": ["澳大利亚", "澳洲", "Australia", "AU", "AUS"]},
}


def _tmdb_api_key(arg: str | None) -> str:
    return arg or os.environ.get("TMDB_API_KEY") or str((settings.get("app") or {}).get("rmt_tmdbkey") or "")


def _fetch_tmdb(api_key: str, client: httpx.Client) -> dict[str, list[dict[str, Any]]]:
    if not api_key:
        return {}
    base = "https://api.themoviedb.org/3"
    result: dict[str, list[dict[str, Any]]] = {}
    for kind in ("movie", "tv"):
        try:
            response = client.get(
                f"{base}/genre/{kind}/list",
                params={"api_key": api_key, "language": "zh-CN"},
                timeout=20,
            )
            response.raise_for_status()
            result[kind] = list(response.json().get("genres") or [])
        except (httpx.HTTPError, ValueError):
            continue
    return result


def _fetch_douban_aliases(client: httpx.Client) -> set[str]:
    try:
        response = client.get(
            "https://movie.douban.com/tag/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return set()
    values = set(re.findall(r"[?&]tags=([^&\"']+)", response.text))
    return {value.strip() for value in values if value.strip()}


def _tmdb_key_for(genre_id: int, kind: str, seed_index: dict[tuple[int, str], str]) -> str:
    return seed_index.get((genre_id, kind), f"tmdb_{kind}_{genre_id}")


def build_taxonomy(tmdb: dict[str, list[dict[str, Any]]], douban_aliases: set[str]) -> dict[str, Any]:
    genres: dict[str, dict[str, Any]] = {}
    for seed in GENRE_SEEDS:
        item = {
            "labels": {"zh": seed["zh"], "en": seed["en"]},
            "tmdb": seed["tmdb"],
            "aliases": list(dict.fromkeys([seed["zh"], seed["en"], *seed["aliases"]])),
        }
        genres[seed["key"]] = item

    seed_index = {
        (int(genre_id), kind): seed["key"]
        for seed in GENRE_SEEDS
        for kind, ids in seed["tmdb"].items()
        for genre_id in ids
    }
    for kind, rows in tmdb.items():
        for row in rows:
            raw_id = row.get("id")
            if raw_id is None:
                continue
            try:
                genre_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            key = _tmdb_key_for(genre_id, kind, seed_index)
            item = genres.setdefault(
                key,
                {
                    "labels": {"zh": str(row.get("name") or key), "en": str(row.get("name") or key)},
                    "tmdb": {},
                    "aliases": [str(row.get("name") or key)],
                },
            )
            item["tmdb"].setdefault(kind, [])
            if genre_id not in item["tmdb"][kind]:
                item["tmdb"][kind].append(genre_id)
            name = str(row.get("name") or "").strip()
            if name and name not in item["aliases"]:
                item["aliases"].append(name)

    alias_to_key = {
        alias.strip().lower(): key for key, item in genres.items() for alias in item["aliases"] if alias.strip()
    }
    for alias in douban_aliases:
        key = alias_to_key.get(alias.lower())
        if key and alias not in genres[key]["aliases"]:
            genres[key]["aliases"].append(alias)

    return {
        "version": 1,
        "genres": genres,
        "languages": {
            key: {
                "labels": {"zh": item["zh"], "en": item["en"]},
                "aliases": list(dict.fromkeys([item["zh"], item["en"], *item["aliases"]])),
            }
            for key, item in LANGUAGE_SEEDS.items()
        },
        "countries": {
            key: {
                "labels": {"zh": item["zh"], "en": item["en"]},
                "aliases": list(dict.fromkeys([item["zh"], item["en"], *item["aliases"]])),
            }
            for key, item in COUNTRY_SEEDS.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成分类 taxonomy.json（一次性维护）")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true", help="不访问 TMDB/豆瓣，仅使用内置映射")
    parser.add_argument("--douban", action="store_true", help="额外从豆瓣标签页收集中文别名")
    parser.add_argument("--tmdb-api-key", default=None)
    args = parser.parse_args()

    tmdb: dict[str, list[dict[str, Any]]] = {}
    douban_aliases: set[str] = set()
    if not args.offline:
        with httpx.Client(follow_redirects=True) as client:
            tmdb = _fetch_tmdb(_tmdb_api_key(args.tmdb_api_key), client)
            if args.douban:
                douban_aliases = _fetch_douban_aliases(client)

    taxonomy = build_taxonomy(tmdb, douban_aliases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"已写入 {args.output}：{len(taxonomy['genres'])} 个类型，"
        f"{len(taxonomy['languages'])} 种语言，{len(taxonomy['countries'])} 个国家/地区"
    )
    if args.douban and not douban_aliases:
        print("提示：豆瓣标签页未获取到别名，已仅使用内置映射")


if __name__ == "__main__":
    main()
