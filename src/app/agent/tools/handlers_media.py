"""Media related handlers — 媒体搜索/过滤/下载/订阅."""

from typing import Any

import log
from app.agent.tools.base import ToolResult
from app.domain.enums import SearchType
from app.domain.mediatypes import MediaType
from app.infrastructure.cache_system import get_cache_manager
from app.media.models import MediaInfo

_MEDIA_TYPE_MAP = {"movie": MediaType.MOVIE, "tv": MediaType.TV, "anime": MediaType.ANIME}
_search_cache = get_cache_manager().get_or_create("agent_media_search", cache_type="memory", maxsize=200, ttl=60)


def _search_cache_key(query: str, media_type: str, year: int, season: int, episode: int) -> str:
    return f"{query}:{media_type}:{year}:{season}:{episode}"


def media_search(
    deps: dict[str, Any],
    query: str,
    media_type: str = "",
    year: int = 0,
    season: int = 0,
    episode: int = 0,
    limit: int = 10,
    **_,
) -> ToolResult:
    cache_key = _search_cache_key(query, media_type, year, season, episode)
    cached = _search_cache.get(cache_key)
    if cached is not None:
        log.debug(f"[media_search] 命中缓存: {query}")
        return ToolResult(success=True, data=cached)

    intent_agent = deps["search_intent_agent"]
    intent = intent_agent.parse(query) if intent_agent.ready else None
    keywords = intent.keywords if intent else query

    media = deps["media_service"]
    indexer = deps["indexer_service"]
    media_info = media.get_media_info(title=keywords)
    if not media_info or not media_info.title:
        return ToolResult(success=False, error=f"无法识别媒体: {keywords}")

    filter_args = {
        "year": year or (intent.year if intent else 0),
        "season": [season or (intent.season if intent else 0)]
        if (season or (intent.season if intent else 0))
        else None,
        "episode": [episode or (intent.episode if intent else 0)]
        if (episode or (intent.episode if intent else 0))
        else None,
        "type": media_type or (intent.media_type if intent else ""),
        "seeders": True,
    }

    results = indexer.search_by_keyword(
        key_word=media_info.title,
        filter_args=filter_args,
        match_media=media_info,
    )
    if not results:
        return ToolResult(success=True, data=f"未找到 '{keywords}' 的资源")

    formatted = []
    for r in results[:limit]:
        formatted.append(
            {
                "title": getattr(r, "title", "") or getattr(r, "org_string", ""),
                "site": getattr(r, "site", ""),
                "size": getattr(r, "size", 0),
                "seeders": getattr(r, "seeders", 0),
                "enclosure": getattr(r, "enclosure", ""),
            }
        )
    data = {
        "query": query,
        "keywords": keywords,
        "media_title": media_info.title,
        "results_count": len(results),
        "results": formatted,
    }
    _search_cache.set(cache_key, data)
    return ToolResult(success=True, data=data)


def _parse_size_gb(s: str) -> float:
    if not s:
        return 0
    s = s.upper().replace(",", "")
    try:
        if "TB" in s:
            return float(s.replace("TB", "").strip()) * 1024
        if "GB" in s:
            return float(s.replace("GB", "").strip())
        if "MB" in s:
            return float(s.replace("MB", "").strip()) / 1024
    except ValueError:
        pass
    return float("inf")


def resource_filter(
    resources: list,
    min_seeders: int = 0,
    max_size_gb: float = 0,
    sites: list | None = None,
    exclude_sites: list | None = None,
    sort_by: str = "seeders",
    preferred_qualities: list | None = None,
    **_,
) -> ToolResult:
    filtered = resources.copy()

    if min_seeders > 0:
        filtered = [r for r in filtered if r.get("seeders", 0) >= min_seeders]

    if max_size_gb > 0:
        filtered = [r for r in filtered if _parse_size_gb(r.get("size", "")) <= max_size_gb]

    if sites:
        filtered = [r for r in filtered if r.get("site", "") in sites]
    if exclude_sites:
        filtered = [r for r in filtered if r.get("site", "") not in exclude_sites]

    if preferred_qualities:

        def _score(r):
            title = r.get("title", "")
            return sum(
                len(preferred_qualities) - i for i, q in enumerate(preferred_qualities) if q.lower() in title.lower()
            )

        filtered.sort(key=_score, reverse=True)

    if sort_by == "seeders":
        filtered.sort(key=lambda r: r.get("seeders", 0), reverse=True)
    elif sort_by == "site":
        filtered.sort(key=lambda r: r.get("site", ""))

    return ToolResult(
        success=True,
        data={
            "original_count": len(resources),
            "filtered_count": len(filtered),
            "results": filtered,
        },
    )


def media_download(
    deps: dict[str, Any],
    title: str = "",
    media_type: str = "",
    year: int = 0,
    enclosure: str = "",
    site: str = "",
    size: str = "",
    season: int = 0,
    episode: int = 0,
    **_,
) -> ToolResult:
    if enclosure:
        media_info = deps["media_service"].get_media_info(title=title)
        if not media_info:
            media_info = MediaInfo()
            media_info.title = title or "未知资源"
        media_info.org_string = title or ""
        media_info.enclosure = enclosure
        media_info.site = site
        if season:
            media_info.begin_season = season
        if episode:
            media_info.begin_episode = episode
        deps["downloader_core"].download(media_info=media_info)
        return ToolResult(success=True, data=f"已开始下载: {media_info.title}")

    if not title:
        return ToolResult(success=False, error="需要提供 title 或 enclosure")

    media_info = deps["media_service"].get_media_info(title=title)
    if not media_info or not media_info.title:
        return ToolResult(success=False, error=f"无法识别媒体: {title}")
    media_info.org_string = title

    if media_type:
        media_info.type = _MEDIA_TYPE_MAP.get(media_type, media_info.type)

    searcher = deps["searcher"]
    search_result, no_exists, search_count, download_count = searcher.search_one_media(
        media_info=media_info, in_from=SearchType.API, no_exists={}
    )

    if not search_count:
        return ToolResult(success=False, error=f"未搜索到 '{title}' 的资源")
    if download_count:
        return ToolResult(success=True, data=f"'{title}' 搜索成功，已下载 {download_count} 个资源")
    return ToolResult(success=True, data=f"'{title}' 搜索到 {search_count} 个结果，但未匹配到符合下载条件的资源")


def media_subscribe(
    deps: dict[str, Any],
    title: str,
    media_type: str,
    year: int = 0,
    season: int = 0,
    tmdbid: str = "",
    **_,
) -> ToolResult:
    media_info = deps["media_service"].get_media_info(title=title)
    if not media_info or not media_info.title:
        return ToolResult(success=False, error=f"无法识别媒体: {title}")

    if media_type:
        media_info.type = _MEDIA_TYPE_MAP.get(media_type, media_info.type)

    mediaid = tmdbid or media_info.tmdb_id
    if mediaid:
        mediaid = str(mediaid)
    else:
        mediaid = None

    code, msg, media_info = deps["subscribe_service"].add_rss_subscribe(
        mtype=media_info.type,
        name=media_info.title,
        year=media_info.year,
        season=season or media_info.begin_season,
        mediaid=mediaid,
        channel="auto",
    )

    if code == 0:
        return ToolResult(success=True, data=f"已添加订阅: {media_info.get_title_string()}")
    return ToolResult(success=False, error=f"添加订阅失败: {msg}")
