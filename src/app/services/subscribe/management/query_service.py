"""Subscribe query service - 订阅查询与删除."""

import re
from datetime import date
from typing import Any

import log
from app.core.constants import ANIME_GENREIDS
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.db.repositories.media_series_repository import MediaSeriesRepository
from app.domain.entities.custom_rss import custom_rss_id
from app.domain.mediatypes import MediaType
from app.media.display_image_policy import transform_display_image
from app.media.metadata.gateway import MetadataGateway
from app.schemas.auth import UserContext
from app.services.search_subject import SearchSubject
from app.services.subscribe.management.utils import parse_rss_desc
from app.utils.json_utils import JsonUtils

_ANIME_GENRE_NAMES = {"动画", "動畫", "アニメ", "animation"}
_ANIME_GENRE_IDS = set(ANIME_GENREIDS)


def _genres_are_anime(genres) -> bool:
    for genre in genres or []:
        text = str(genre).strip()
        if not text:
            continue
        if text.upper() in _ANIME_GENRE_IDS or text.lower() in _ANIME_GENRE_NAMES:
            return True
    return False


def _resolve_subscribe_type(value, tmdbid=None, genres=None, metadata_gateway: MetadataGateway | None = None) -> str:
    """订阅媒体类型归一化：movie/tv/anime.

    历史订阅未把 media_type 写入 NOTE 时，回退用 TMDB 缓存 genres 判断是否为动漫，
    避免"全部是动漫却有部分显示电视剧"。
    """
    parsed = MediaType.from_string(str(value or ""))
    if parsed == MediaType.MOVIE:
        return MediaType.MOVIE.value
    if parsed == MediaType.ANIME:
        return MediaType.ANIME.value
    # NOTE 中持久化的通用题材优先（TMDB/豆瓣/插件都可能写入）
    if _genres_are_anime(genres):
        return MediaType.ANIME.value
    # TV 或缺失类型都继续用 TMDB genres 判定：历史动漫订阅通常 media_type=tv，
    # 但实际是动画，不能因为 NOTE 里有 media_type 就直接当成电视剧。
    if tmdbid and metadata_gateway is None:
        log.warn(f"[Subscribe]缺少 MetadataGateway，无法推断订阅类型: {tmdbid}")
        return MediaType.UNKNOWN.value
    if tmdbid and metadata_gateway is not None:
        try:
            # TMDB 详情缓存可能带不同 append_to_response 后缀，逐一尝试已知形态，
            # 否则会误判为缓存未命中并把动漫降级成电视剧。
            genre_ids = metadata_gateway.genres(
                "tmdb",
                tmdbid,
                media_type=MediaType.TV,
                extras=(
                    "",
                    "credits,images,external_ids",
                    "all",
                    "alternative_titles,translations",
                ),
            )
            if genre_ids.intersection(ANIME_GENREIDS):
                return MediaType.ANIME.value
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Subscribe]推断订阅类型失败 {tmdbid}: {e!s}")
    return MediaType.TV.value


_REF_PREFIX_ALIASES = {
    "db": "douban",
    "douban": "douban",
    "bgm": "bangumi",
    "bg": "bangumi",
    "bangumi": "bangumi",
    "tmdb": "tmdb",
}


def _source_label(
    provider: str,
    raw_id: str | None = None,
    metadata_ref: str | None = None,
    source_provider: str | None = None,
    metadata_gateway: MetadataGateway | None = None,
) -> str:
    """来源展示名：优先真实订阅来源，虚拟元数据 provider 不作为来源。"""
    value = str(provider or "").strip().lower()
    ref = str(metadata_ref or raw_id or "").strip()
    if (not value or value == "content_id") and ref and ":" in ref:
        prefix = ref.split(":", 1)[0].strip().lower()
        value = _REF_PREFIX_ALIASES.get(prefix, prefix)
    if value == "content_id":
        return "插件"
    is_virtual = metadata_gateway is not None and metadata_gateway.provider_is_virtual(value)
    if is_virtual and source_provider and metadata_gateway is not None:
        real = str(source_provider).strip().lower()
        return metadata_gateway.provider_display_name(real) or source_provider
    if is_virtual:
        return "未知来源"
    return metadata_gateway.provider_display_name(value) if metadata_gateway is not None else (value or "未知")


def _normalized_anchor(provider, external_id) -> tuple[str | None, str | None]:
    value = str(provider or "").strip()
    external = str(external_id or "").strip()
    if external.startswith("content_id:"):
        return "content_id", external.split(":", 1)[1]
    if value == "content_id" and not external:
        return value, None
    return value or None, external or None


def _canonical_ref(row) -> str:
    """统一身份输出：metadata_ref > identity > anchor > tmdb."""
    explicit = str(getattr(row, "METADATA_REF", "") or "").strip()
    if explicit:
        return explicit
    identity_id = str(getattr(row, "IDENTITY_ID", "") or "").strip()
    if identity_id:
        return f"id:{identity_id}"
    provider, external = _normalized_anchor(
        getattr(row, "ANCHOR_PROVIDER", None), getattr(row, "ANCHOR_EXTERNAL_ID", None)
    )
    if provider and external:
        return f"{provider}:{external}"
    tmdbid = str(getattr(row, "TMDBID", "") or "").strip()
    return f"tmdb:{tmdbid}" if tmdbid.isdigit() else ""


class SubscribeQueryService:
    """订阅查询服务"""

    def __init__(
        self,
        movie_repo,
        tv_repo,
        tv_episode_repo,
        history_repo,
        sites,
        indexer_service,
        user_repo=None,
        *,
        metadata_gateway: MetadataGateway,
    ):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._tv_episode_repo = tv_episode_repo
        self._history_repo = history_repo
        self._sites = sites
        self._indexer_service = indexer_service
        self._user_repo = user_repo
        self._metadata_gateway = metadata_gateway

    def _usernames(self, rows) -> dict[int, str]:
        """批量解析订阅归属用户名（无 user_repo 时返回空映射）"""
        if self._user_repo is None:
            return {}
        ids = list({r.USER_ID for r in rows if getattr(r, "USER_ID", None)})
        return self._user_repo.get_usernames_by_ids(ids) if ids else {}

    def get_subscription_count(self, user: UserContext | None = None) -> dict[str, Any]:
        """首页统计：返回全部内容画像的订阅数，不再只统计 default."""
        movies = self._movie_repo.get_all(user=user)
        tvs = self._tv_repo.get_all(user=user)
        today = date.today().isoformat()

        def is_today(item) -> bool:
            value = getattr(item, "add_date", None) or getattr(item, "ADD_DATE", None) or ""
            return str(value)[:10] == today

        profiles: dict[str, int] = {}
        for item in [*movies, *tvs]:
            key = str(getattr(item, "CONTENT_PROFILE", None) or getattr(item, "content_profile", None) or "default")
            profiles[key] = profiles.get(key, 0) + 1
        return {
            "movie": len(movies),
            "tv": len(tvs),
            "total": len(movies) + len(tvs),
            "new_today": sum(1 for item in movies if is_today(item)) + sum(1 for item in tvs if is_today(item)),
            "profiles": profiles,
        }

    @staticmethod
    def _attach_aliases(items: dict) -> dict:
        identity_ids = {str(item.get("identity_id")) for item in items.values() if item.get("identity_id")}
        if not identity_ids:
            return items
        try:
            aliases_map = MediaIdentityRepository().get_aliases_map(identity_ids)
        except Exception as exc:  # noqa: BLE001 - 别名只用于预筛，不影响订阅列表
            log.debug(f"[Subscribe]读取订阅别名失败: {exc}")
            return items
        for item in items.values():
            item["aliases"] = aliases_map.get(str(item.get("identity_id")), [])
        return items

    def get_subscribe_movies(
        self, rid: int | None = None, state: str | None = None, user: UserContext | None = None
    ) -> dict:
        """获取电影订阅（user 非空时按数据归属过滤）"""
        ret_dict = {}
        rss_movies = self._movie_repo.get_all(rssid=rid, state=state, user=user)
        usernames = self._usernames(rss_movies)
        rss_sites_valid = self._sites.get_site_names(rss=True)
        search_sites_valid = self._indexer_service.get_user_indexer_names()
        for rss_movie in rss_movies:
            desc = rss_movie.DESC
            note = rss_movie.NOTE
            tmdbid = rss_movie.TMDBID
            rss_sites = JsonUtils.loads(rss_movie.RSS_SITES) if rss_movie.RSS_SITES else []
            search_sites = JsonUtils.loads(rss_movie.SEARCH_SITES) if rss_movie.SEARCH_SITES else []
            over_edition = rss_movie.OVER_EDITION == 1
            filter_restype = rss_movie.FILTER_RESTYPE
            filter_pix = rss_movie.FILTER_PIX
            filter_team = rss_movie.FILTER_TEAM
            filter_rule = rss_movie.FILTER_RULE
            filter_include = rss_movie.FILTER_INCLUDE
            filter_exclude = rss_movie.FILTER_EXCLUDE
            filter_free = bool(rss_movie.FILTER_FREE)
            download_setting = rss_movie.DOWNLOAD_SETTING
            save_path = rss_movie.SAVE_PATH
            fuzzy_match = rss_movie.FUZZY_MATCH == 1
            keyword = rss_movie.KEYWORD
            if keyword and str(keyword).startswith("content_id:"):
                keyword = str(keyword).split(":", 1)[1]
            if desc and desc.find("{") != -1:
                desc = parse_rss_desc(desc)
                rss_sites = desc.get("rss_sites")
                search_sites = desc.get("search_sites")
                over_edition = desc.get("over_edition") == "Y"
                filter_restype = desc.get("restype")
                filter_pix = desc.get("pix")
                filter_team = desc.get("team")
                filter_rule = desc.get("rule")
                download_setting = ""
                save_path = ""
                fuzzy_match = not tmdbid
            if note:
                note_info = parse_rss_desc(note)
            else:
                note_info = {}
            rss_sites = [
                site for site in (rss_sites or []) if site in rss_sites_valid or custom_rss_id(site) is not None
            ]
            search_sites = [site for site in (search_sites or []) if site in search_sites_valid]
            anchor_provider, anchor_external_id = _normalized_anchor(
                rss_movie.ANCHOR_PROVIDER, rss_movie.ANCHOR_EXTERNAL_ID
            )
            metadata_ref = _canonical_ref(rss_movie)
            if not keyword and anchor_external_id and rss_movie.CONTENT_PROFILE not in (None, "", "default"):
                keyword = anchor_external_id
            ret_dict[str(rss_movie.ID)] = {
                "id": rss_movie.ID,
                "user_id": rss_movie.USER_ID,
                "username": usernames.get(rss_movie.USER_ID) if rss_movie.USER_ID else None,
                "name": rss_movie.NAME,
                "year": rss_movie.YEAR,
                "tmdbid": rss_movie.TMDBID if metadata_ref.startswith("tmdb:") else "",
                "identity_id": rss_movie.IDENTITY_ID,
                "anchor_provider": anchor_provider,
                "anchor_external_id": anchor_external_id,
                "provider": getattr(rss_movie, "PROVIDER", None),
                "metadata_ref": metadata_ref,
                "source_label": _source_label(
                    getattr(rss_movie, "PROVIDER", None) or anchor_provider or "",
                    rss_movie.TMDBID,
                    getattr(rss_movie, "METADATA_REF", None),
                    note_info.get("source_provider"),
                    metadata_gateway=self._metadata_gateway,
                ),
                "content_profile": rss_movie.CONTENT_PROFILE,
                "metadata_policy": rss_movie.METADATA_POLICY,
                "naming_profile": rss_movie.NAMING_PROFILE,
                "image": transform_display_image(
                    str(getattr(rss_movie, "CONTENT_PROFILE", "") or ""),
                    str(rss_movie.IMAGE or ""),
                ),
                "overview": rss_movie.DESC,
                "rss_sites": rss_sites,
                "search_sites": search_sites,
                "over_edition": over_edition,
                "filter_restype": filter_restype,
                "filter_pix": filter_pix,
                "filter_team": filter_team,
                "filter_rule": filter_rule,
                "filter_include": filter_include,
                "filter_exclude": filter_exclude,
                "filter_free": filter_free,
                "save_path": save_path,
                "download_setting": download_setting,
                "fuzzy_match": fuzzy_match,
                "state": rss_movie.STATE,
                "retry_count": int(getattr(rss_movie, "RETRY_COUNT", 0) or 0),
                "next_retry_at": getattr(rss_movie, "NEXT_RETRY_AT", None),
                "poster": note_info.get("poster"),
                "release_date": note_info.get("release_date"),
                "vote": note_info.get("vote"),
                "keyword": keyword,
                "type": MediaType.MOVIE.value,
                "add_date": rss_movie.ADD_DATE,
            }
        return self._attach_aliases(ret_dict)

    def get_subscribe_tvs(
        self, rid: int | None = None, state: str | None = None, user: UserContext | None = None
    ) -> dict:
        """获取电视剧订阅（user 非空时按数据归属过滤）"""
        ret_dict = {}
        try:
            series_map = {row.SERIES_KEY: row for row in MediaSeriesRepository().list_series(limit=500)}
        except Exception:
            series_map = {}
        rss_tvs = self._tv_repo.get_all(rssid=rid, state=state, user=user)
        usernames = self._usernames(rss_tvs)
        rss_sites_valid = self._sites.get_site_names(rss=True)
        search_sites_valid = self._indexer_service.get_user_indexer_names()
        for rss_tv in rss_tvs:
            desc = rss_tv.DESC
            note = rss_tv.NOTE
            tmdbid = rss_tv.TMDBID
            rss_sites = JsonUtils.loads(rss_tv.RSS_SITES) if rss_tv.RSS_SITES else []
            search_sites = JsonUtils.loads(rss_tv.SEARCH_SITES) if rss_tv.SEARCH_SITES else []
            over_edition = rss_tv.OVER_EDITION == 1
            filter_restype = rss_tv.FILTER_RESTYPE
            filter_pix = rss_tv.FILTER_PIX
            filter_team = rss_tv.FILTER_TEAM
            filter_rule = rss_tv.FILTER_RULE
            filter_include = rss_tv.FILTER_INCLUDE
            filter_exclude = rss_tv.FILTER_EXCLUDE
            filter_free = bool(rss_tv.FILTER_FREE)
            download_setting = rss_tv.DOWNLOAD_SETTING
            save_path = rss_tv.SAVE_PATH
            total_ep = rss_tv.TOTAL_EP
            current_ep = rss_tv.CURRENT_EP
            total = int(rss_tv.TOTAL or 0)
            lack = int(rss_tv.LACK or 0)
            # 进度以 CURRENT_EP（首个待下载集）为准；历史数据可能 LACK 与 CURRENT_EP 不一致。
            if total and current_ep and 0 < int(current_ep) <= total:
                lack = max(0, total - int(current_ep) + 1)
            fuzzy_match = rss_tv.FUZZY_MATCH == 1
            keyword = rss_tv.KEYWORD
            if keyword and str(keyword).startswith("content_id:"):
                keyword = str(keyword).split(":", 1)[1]
            if desc and desc.find("{") != -1:
                desc = parse_rss_desc(desc)
                rss_sites = desc.get("rss_sites")
                search_sites = desc.get("search_sites")
                over_edition = desc.get("over_edition") == "Y"
                filter_restype = desc.get("restype")
                filter_pix = desc.get("pix")
                filter_team = desc.get("team")
                filter_rule = desc.get("rule")
                filter_include = desc.get("include")
                filter_exclude = desc.get("exclude")
                save_path = ""
                download_setting = ""
                total_ep = desc.get("total")
                current_ep = desc.get("current")
                fuzzy_match = not tmdbid
            if note:
                note_info = parse_rss_desc(note)
            else:
                note_info = {}
            rss_sites = [
                site for site in (rss_sites or []) if site in rss_sites_valid or custom_rss_id(site) is not None
            ]
            search_sites = [site for site in (search_sites or []) if site in search_sites_valid]
            anchor_provider, anchor_external_id = _normalized_anchor(rss_tv.ANCHOR_PROVIDER, rss_tv.ANCHOR_EXTERNAL_ID)
            metadata_ref = _canonical_ref(rss_tv)
            subject = SearchSubject.classify(
                note_info.get("media_type"),
                rss_tv.CONTENT_PROFILE,
                anchor_provider,
                anchor_external_id or tmdbid,
            )
            resolved_type = (
                subject.display_type.value
                if subject.display_type
                else _resolve_subscribe_type(
                    note_info.get("media_type"),
                    tmdbid,
                    note_info.get("genres"),
                    metadata_gateway=self._metadata_gateway,
                )
            )
            # 历史动漫订阅可能仍是 default 画像；序列化时按实际类型归到 anime 画像，
            # 列表 tab 才能同时满足“展示为动漫”和“出现在动漫 tab”。
            effective_profile = "anime" if resolved_type == "anime" else (rss_tv.CONTENT_PROFILE or "default")
            # 旧动漫订阅可能把 Bangumi/锚点 ID 存成关键词；对动漫回退到标题。
            if resolved_type == "anime" and keyword:
                keyword_text = str(keyword).strip()
                if keyword_text == str(anchor_external_id or "") or (
                    anchor_provider == "bangumi" and keyword_text.isdigit()
                ):
                    keyword = rss_tv.NAME
            series_row = series_map.get(getattr(rss_tv, "SERIES_KEY", None) or "")
            ret_dict[str(rss_tv.ID)] = {
                "id": rss_tv.ID,
                "user_id": rss_tv.USER_ID,
                "username": usernames.get(rss_tv.USER_ID) if rss_tv.USER_ID else None,
                "name": rss_tv.NAME,
                "year": rss_tv.YEAR,
                "season": rss_tv.SEASON,
                "tmdbid": rss_tv.TMDBID if metadata_ref.startswith("tmdb:") else "",
                "identity_id": rss_tv.IDENTITY_ID,
                "series_key": getattr(rss_tv, "SERIES_KEY", None),
                "series_title": series_row.TITLE if series_row else None,
                "series_total_seasons": series_row.TOTAL_SEASONS if series_row else None,
                "anchor_provider": anchor_provider,
                "anchor_external_id": anchor_external_id,
                "provider": getattr(rss_tv, "PROVIDER", None),
                "metadata_ref": metadata_ref,
                "source_label": _source_label(
                    getattr(rss_tv, "PROVIDER", None) or anchor_provider or "",
                    rss_tv.TMDBID,
                    getattr(rss_tv, "METADATA_REF", None),
                    note_info.get("source_provider"),
                    metadata_gateway=self._metadata_gateway,
                ),
                "content_profile": effective_profile,
                "metadata_policy": rss_tv.METADATA_POLICY,
                "naming_profile": rss_tv.NAMING_PROFILE,
                "image": transform_display_image(
                    str(effective_profile or ""),
                    str(rss_tv.IMAGE or ""),
                ),
                "overview": rss_tv.DESC,
                "rss_sites": rss_sites,
                "search_sites": search_sites,
                "over_edition": over_edition,
                "filter_restype": filter_restype,
                "filter_pix": filter_pix,
                "filter_team": filter_team,
                "filter_rule": filter_rule,
                "filter_include": filter_include,
                "filter_exclude": filter_exclude,
                "filter_free": filter_free,
                "save_path": save_path,
                "download_setting": download_setting,
                "total": total,
                "lack": lack,
                "total_ep": total_ep,
                "current_ep": current_ep,
                "fuzzy_match": fuzzy_match,
                "state": rss_tv.STATE,
                "retry_count": int(getattr(rss_tv, "RETRY_COUNT", 0) or 0),
                "next_retry_at": getattr(rss_tv, "NEXT_RETRY_AT", None),
                "poster": note_info.get("poster"),
                "release_date": note_info.get("release_date"),
                "vote": note_info.get("vote"),
                "keyword": keyword,
                "type": resolved_type,
                "add_date": rss_tv.ADD_DATE,
            }
        return self._attach_aliases(ret_dict)

    def get_subscribe_tv_episodes(self, rssid: int | None) -> Any:
        """查询数据库中订阅的电视剧缺失集数"""
        return self._tv_episode_repo.get(int(rssid or 0))

    def get_subscribe_by_anchor(
        self,
        anchor_provider: str | None,
        anchor_external_id: str | None,
        mtype: MediaType,
        user: UserContext | None = None,
    ) -> dict | None:
        """按 ANCHOR_PROVIDER/ANCHOR_EXTERNAL_ID 查询订阅（DB/插件锚点）."""
        provider = str(anchor_provider or "").strip()
        external = str(anchor_external_id or "").strip()
        if not provider or not external:
            return None
        repo = self._movie_repo if mtype == MediaType.MOVIE else self._tv_repo
        legacy_ref = f"DB:{external}" if provider == "douban" else f"BG:{external}" if provider == "bangumi" else ""
        for row in repo.get_all(user=user):
            anchor_match = (
                str(getattr(row, "anchor_provider", "") or "") == provider
                and str(getattr(row, "anchor_external_id", "") or "") == external
            )
            legacy_match = bool(legacy_ref) and str(getattr(row, "tmdb_id", "") or "").strip() == legacy_ref
            if anchor_match or legacy_match:
                seasons = self._parse_season_numbers(getattr(row, "season", None)) if mtype != MediaType.MOVIE else []
                return {
                    "rssid": str(row.id),
                    "fav": "1",
                    "sub_seasons": seasons,
                    "state": getattr(row, "state", ""),
                }
        return None

    def get_subscribe_seasons(
        self,
        tmdbid: str | None = None,
        title: str | None = None,
        year: str | None = None,
        user: UserContext | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
    ) -> list[int]:
        """获取某部剧集已订阅的季号列表

        SEASON 存储格式为 "S01" 或 "S01-S03"（区间），此处解析为季号整数列表。
        优先按 tmdbid 匹配，其次按名称(+年份)匹配。user 非空时按数据归属过滤。
        """
        seasons: set[int] = set()
        tmdbid_str = str(tmdbid) if tmdbid else ""
        for rss_tv in self._tv_repo.get_all(user=user):
            matched = False
            if anchor_provider and anchor_external_id:
                matched = (
                    str(getattr(rss_tv, "anchor_provider", "") or "") == anchor_provider
                    and str(getattr(rss_tv, "anchor_external_id", "") or "") == anchor_external_id
                )
            elif tmdbid_str and str(rss_tv.tmdb_id) == tmdbid_str:
                matched = True
            elif not tmdbid_str and title and rss_tv.name == title:
                matched = not year or str(rss_tv.year) == str(year)
            if not matched:
                continue
            seasons.update(self._parse_season_numbers(rss_tv.season))
        return sorted(seasons)

    def get_subscribe_id_by_anchor(
        self,
        mtype: MediaType,
        anchor_provider: str | None,
        anchor_external_id: str | None,
        season: str | None = None,
        user: UserContext | None = None,
    ) -> int | None:
        if not anchor_provider or not anchor_external_id:
            return None
        rows = self._movie_repo.get_all(user=user) if mtype == MediaType.MOVIE else self._tv_repo.get_all(user=user)
        for row in rows:
            if (
                str(getattr(row, "anchor_provider", "") or "") == anchor_provider
                and str(getattr(row, "anchor_external_id", "") or "") == anchor_external_id
                and (season is None or str(getattr(row, "season", "") or "") == season)
            ):
                return int(row.id)
        return None

    @staticmethod
    def _parse_season_numbers(season_str: str | None) -> list[int]:
        """将 "S01" / "S01-S03" 解析为季号整数列表"""
        if not season_str:
            return []
        nums = [int(n) for n in re.findall(r"S(\d+)", season_str, flags=re.IGNORECASE)]
        if len(nums) == 2 and nums[0] <= nums[1]:
            return list(range(nums[0], nums[1] + 1))
        return nums

    def check_history(self, type_str: str, name: str, year: str | None, season: str | None) -> bool:
        """检查订阅历史是否存在"""
        return self._history_repo.check_exists(type_str=type_str, name=name, year=year or "", season=season or "")

    def delete_subscribe(
        self,
        mtype: MediaType,
        title: str | None = None,
        year: str | None = None,
        season: str | None = None,
        rssid: int | None = None,
        tmdbid: str | None = None,
        user: UserContext | None = None,
    ) -> Any:
        """删除订阅（user 非空且非超管时仅可删除自己的订阅）.

        有 rssid 时只按 rssid 删除，避免插件标题/搜索标题与订阅名不一致导致删不掉。
        """
        if rssid is not None:
            if mtype == MediaType.MOVIE:
                return self._movie_repo.delete(rssid=rssid, user=user)
            return self._tv_repo.delete(rssid=rssid, user=user)
        if mtype == MediaType.MOVIE:
            return self._movie_repo.delete(title=title, year=year, rssid=None, tmdbid=tmdbid, user=user)
        return self._tv_repo.delete(title=title, season=season, rssid=None, tmdbid=tmdbid, user=user)

    def get_history_id(self, mtype, title, year=None, tmdbid=None):
        """查询已完成的订阅历史 ID（用于"订阅完成"标识）."""
        rtype = mtype.value if hasattr(mtype, "value") else str(mtype or "")
        return self._history_repo.get_rss_history_id(rtype, title, year, tmdbid)

    def get_subscribe_id(
        self,
        mtype: MediaType,
        title: str,
        year: str | None = None,
        season: str | None = None,
        tmdbid: str | None = None,
        user_id: int | None = None,
        content_profile: str | None = None,
    ) -> Any:
        """获取订阅ID（按归属用户与内容画像收敛）"""
        if mtype == MediaType.MOVIE:
            return self._movie_repo.get_id(
                title=title, year=year, tmdbid=tmdbid, user_id=user_id, content_profile=content_profile
            )
        else:
            return self._tv_repo.get_id(
                title=title,
                year=year,
                season=season,
                tmdbid=tmdbid,
                user_id=user_id,
                content_profile=content_profile,
            )
