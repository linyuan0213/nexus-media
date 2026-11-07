import re
from concurrent.futures import ThreadPoolExecutor, wait
from difflib import SequenceMatcher
from typing import Any

import cn2an

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.core.settings import settings
from app.domain.media_types import media_type_registry
from app.domain.media_utils import check_media_exists
from app.domain.mediatypes import MediaType
from app.infrastructure.image_proxy import ImageProxy
from app.media import meta_info
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.media.metadata.parsing import ParserChain
from app.mediaserver import MediaServer
from app.schemas.auth import UserContext
from app.schemas.media import MediaInfoResultDTO, SeasonEpisodesResultDTO
from app.services.subscribe_service import SubscribeService as Subscribe
from app.services.web import mediainfo_dict
from app.services.web.utils import get_mediainfo_from_id, search_media_infos
from app.utils import StringUtils

_KNOWN_REF_RE = re.compile(r"(?i)\b([a-z][a-z0-9_]{1,31}):([A-Za-z0-9._-]{1,64})")
_CONTENT_CODE_RE = re.compile(r"\b([A-Za-z]{2,10}-\d{2,5})\b")
_EPISODE_RE = re.compile(r"(?i)(S\d{1,2}\s*E\d{1,4}|第\s*\d+\s*[集话話]|(?:^|[\s._])\d{1,3}\s*(?:\[|\(|$))")


def _normalize_title(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _title_match_strength(query: str | None, title: str | None) -> float:
    """标题相关性：完全一致/前缀扩展为高分，CM/预告/纯数字尾缀降级."""
    left = _normalize_title(query)
    right = _normalize_title(title)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if right.startswith(left) or left.startswith(right):
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        extra = longer[len(shorter) :]
        if extra and (
            extra.isdigit()
            or any(token in extra for token in ("cm", "pv", "trailer", "预告", "特典", "spinoff", "spin-off"))
        ):
            return 0.45
        return 0.9
    return SequenceMatcher(None, left, right).ratio()


class MediaInfoService:
    """
    媒体信息查询业务服务
    负责 TMDB/豆瓣 媒体信息查询、订阅信息回退、季列表等
    """

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        subscribe: Subscribe,
        media_server: MediaServer,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._subscribe = subscribe
        self._media_server = media_server
        self._metadata_gateway = metadata_gateway

    def _gw(self) -> MetadataGateway:
        if self._metadata_gateway is None:
            raise ServiceError("元数据网关不可用")
        return self._metadata_gateway

    def get_season_episodes(self, tmdbid, title, year, season, content_profile=None) -> SeasonEpisodesResultDTO:
        """查询剧集情况并按目标媒体库检查存在状态"""
        episodes = self._gw().season_episodes("tmdb", tmdbid, season).get("episodes") or []
        for episode in episodes:
            episode.update(
                {
                    "state": bool(
                        self._media_server.check_item_exists(
                            mtype=MediaType.TV,
                            title=title,
                            year=year,
                            tmdbid=tmdbid,
                            season=season,
                            episode=episode.get("episode_number"),
                            content_profile=content_profile,
                        )
                    )
                }
            )
        return SeasonEpisodesResultDTO(episodes=episodes)

    def _douban_record(self, external_id: str, media_type: MediaType) -> dict[str, Any] | None:
        if self._metadata_gateway is None:
            return None
        try:
            return self._metadata_gateway.lookup(
                "douban",
                str(external_id),
                context=MetadataContext(purpose="media.info", allow_private=True),
                media_type=media_type,
            )
        except Exception:  # noqa: BLE001 - 详情失败由调用方决定兜底
            return None

    @staticmethod
    def _record_poster(record: dict[str, Any]) -> str:
        images = record.get("images") or {}
        posters = images.get("poster") or []
        if posters and isinstance(posters[0], dict):
            return str(posters[0].get("url") or "")
        return str(record.get("poster") or "")

    @staticmethod
    def _record_rating(record: dict[str, Any]) -> float | None:
        ratings = record.get("ratings") or {}
        value = ratings.get("douban")
        return float(value) if isinstance(value, (int, float)) else None

    def get_tvseason_list(self, tmdbid, title) -> list[dict]:
        """获取剧集季列表"""
        if title:
            title_season = meta_info(title=title).begin_season
        else:
            title_season = None
        if not str(tmdbid).isdigit():
            media_info = get_mediainfo_from_id(mtype=MediaType.TV, mediaid=tmdbid)
            if not media_info or not media_info.provider_data:
                return []
            season_infos = self._gw().season_summaries(media_info.provider_data)
        else:
            season_infos = self._gw().season_summaries_by_id(tmdbid)
        if title_season:
            return [{"text": f"第{title_season}季", "num": title_season}]
        return [
            {
                "text": "第{}季".format(cn2an.an2cn(season.get("season_number") or 0, mode="low")),
                "num": season.get("season_number"),
            }
            for season in season_infos
        ]

    def get_media_info_detail(self, mediaid, mtype, title, year, page, rssid) -> MediaInfoResultDTO:
        """
        查询媒体信息（优先订阅信息，不足时回退到 TMDB）
        """
        media_type = MediaType.from_string(mtype)
        if media_type == MediaType.UNKNOWN:
            media_type = MediaType.TV

        rssid_ok = False
        seasons: list[dict] = []
        link_url = ""
        vote_average = 0.0
        poster_path = ""
        release_date = ""
        overview = ""

        if rssid:
            rssid = str(rssid)
            if media_type == MediaType.MOVIE:
                rssinfo = self._subscribe.get_subscribe_movies(rid=int(rssid) if rssid else None)
            else:
                rssinfo = self._subscribe.get_subscribe_tvs(rid=int(rssid) if rssid else None)
            if rssinfo:
                overview = rssinfo[rssid].get("overview") or ""
                poster_path = rssinfo[rssid].get("poster") or ""
                title = rssinfo[rssid].get("name") or ""
                vote_average = rssinfo[rssid].get("vote") or 0.0
                year = rssinfo[rssid].get("year") or ""
                release_date = rssinfo[rssid].get("release_date") or ""
                link_url = self._gw().detail_url(media_type, rssinfo[rssid].get("tmdbid"))
                if overview and poster_path:
                    rssid_ok = True

        if not rssid_ok:
            if mediaid:
                media = get_mediainfo_from_id(mtype=media_type, mediaid=mediaid)
            else:
                media = self._gw().resolve_by_title(f"{title} {year}", media_type=media_type)
            if not media or not media.provider_data:
                return MediaInfoResultDTO(
                    type=mtype, type_str=media_type.value, page=page, title=title or "", year=year or ""
                )
            if not mediaid:
                mediaid = media.tmdb_id
            link_url = media.get_detail_url()
            overview = media.overview or ""
            poster_path = media.get_poster_image() or ""
            title = media.title or ""
            vote_average = round(float(media.vote_average or 0), 1)
            year = media.year or ""
            if media_type != MediaType.MOVIE:
                release_date = media.provider_data.get("first_air_date") or ""
                seasons = [
                    {
                        "text": "第{}季".format(cn2an.an2cn(season.get("season_number") or 0, mode="low")),
                        "num": season.get("season_number"),
                    }
                    for season in self._gw().season_summaries(media.provider_data)
                ]
            else:
                release_date = media.provider_data.get("release_date") or ""
            if not rssid:
                rssid = self._subscribe.get_subscribe_id(
                    mtype=media_type, title=title, tmdbid=str(mediaid) if mediaid else None
                )

        if poster_path:
            poster_path = ImageProxy.get_proxy_image_url(
                poster_path, use_proxy=settings.get("app").get("enable_image_proxy", True)
            )

        return MediaInfoResultDTO(
            type=mtype,
            type_str=media_type.value,
            page=page,
            title=title or "",
            vote_average=vote_average,
            poster_path=poster_path,
            release_date=release_date or "",
            year=year or "",
            overview=overview or "",
            link_url=link_url,
            tmdbid=mediaid,
            rssid=rssid,
            seasons=seasons or [],
        )

    def get_media_person(self, tmdbid, mtype_str, keyword) -> Any:
        """查询演员"""
        mtype = media_type_registry.resolve(mtype_str).legacy_type
        if tmdbid:
            return self._gw().person_credits("tmdb", tmdbid, media_type=mtype)
        else:
            return self._gw().search_person(keyword)

    def get_media_recommendations(self, tmdbid, mtype_str, page) -> Any:
        """查询推荐"""
        mtype = media_type_registry.resolve(mtype_str).legacy_type
        if mtype == MediaType.MOVIE:
            return self._gw().related_items("recommendations", tmdbid, media_type=MediaType.MOVIE, page=page)
        else:
            return self._gw().related_items("recommendations", tmdbid, media_type=MediaType.TV, page=page)

    def get_media_similar(self, tmdbid, mtype_str, page) -> Any:
        """查询相似"""
        mtype = media_type_registry.resolve(mtype_str).legacy_type
        if mtype == MediaType.MOVIE:
            return self._gw().related_items("similar", tmdbid, media_type=MediaType.MOVIE, page=page)
        else:
            return self._gw().related_items("similar", tmdbid, media_type=MediaType.TV, page=page)

    def get_person_medias(self, personid, mtype_str, page) -> Any:
        """查询演员参演作品"""
        if mtype_str:
            mtype = media_type_registry.resolve(mtype_str).legacy_type
        else:
            mtype = None
        return self._gw().related_items("person", None, media_type=mtype, page=page, person_id=personid)

    def name_test(self, name, subtitle, user: UserContext | None = None) -> dict:
        """名称识别测试（插件 ParserProfile 优先 + 本地解析 + 多数据源匹配）."""
        # 插件解析器优先：插件声明的内容画像由插件自己识别，不依赖宿主标题解析。
        parsed = ParserChain().extract(name, subtitle or "")
        type_labels = {"movie": "电影", "tv": "剧集", "anime": "动漫"}
        if parsed is not None:
            code = str(getattr(parsed, "anchor_external_id", "") or "")
            display = getattr(parsed, "title_cn", None) or getattr(parsed, "title_en", None) or code or name
            result: dict[str, Any] = {
                "name": display,
                "cn_name": getattr(parsed, "title_cn", None) or display,
                "title": getattr(parsed, "title_en", None) or display,
                "type": type_labels.get(str(getattr(parsed, "type", "")), ""),
                "org_string": name,
                "content_profile": getattr(parsed, "content_profile", "") or "",
                "anchor_provider": getattr(parsed, "anchor_provider", None),
                "anchor_external_id": code or None,
                "confidence": getattr(parsed, "confidence", None),
            }
            query = code or display
            matches, preferred = self._identify_matches(
                name,
                parsed,
                user,
                query=query,
                parsed_profile=getattr(parsed, "content_profile", None),
            )
            best = next((item for item in matches if item.get("preferred")), matches[0] if matches else None)
            if best:
                result.update(
                    {
                        "name": best.get("title") or display,
                        "cn_name": best.get("title") or display,
                        "title": best.get("title") or display,
                        "year": best.get("year") or "",
                        "source_label": best.get("source_label") or "",
                        "image": best.get("poster") or "",
                        "metadata_ref": f"{best.get('provider')}:{best.get('external_id')}",
                        "tmdbid": best.get("external_id") if best.get("provider") == "tmdb" else None,
                    }
                )
            result["matches"] = matches
            result["preferred_source"] = preferred
            return result

        # 非插件解析器覆盖的名称，继续走宿主本地解析。
        media_info = self._gw().resolve_by_title(name, subtitle=subtitle, cache=False)
        result = mediainfo_dict(media_info) if media_info else {"name": "无法识别"}
        matches, preferred = self._identify_matches(name, media_info, user)
        if matches and not result.get("image"):
            result["image"] = next(
                (item.get("poster") for item in matches if item.get("poster")),
                "",
            )
        result["matches"] = matches
        result["preferred_source"] = preferred
        return result

    def _identify_matches(
        self,
        name: str,
        media_info,
        user: UserContext | None,
        *,
        query: str | None = None,
        parsed_profile: str | None = None,
    ):
        """并行查询所有可用元数据源；优先来源排序."""
        if self._metadata_gateway is None:
            return [], None
        allow_private = bool(user and user.has_permission("metadata:private:view"))
        permissions = set(user.permissions) if user else None
        context = MetadataContext(
            user_id=getattr(user, "user_id", None),
            permissions=frozenset(permissions or ()),
            content_profile=str(parsed_profile or "default"),
            purpose="media.identify",
            allow_private=allow_private,
        )
        gateway = self._metadata_gateway
        assert gateway is not None
        providers = gateway.list_providers(allow_private=allow_private, permissions=permissions, probe_health=False)
        searchable = [
            item for item in providers if any("search" in str(cap).lower() for cap in item.get("capabilities", []))
        ]
        # 普通名称不要查内容画像不匹配的插件源，避免无关结果和慢请求。
        wanted_profile = parsed_profile or (
            "anime" if getattr(media_info, "type", None) == MediaType.ANIME else "default"
        )
        searchable = [
            item
            for item in searchable
            if not item.get("content_profiles") or wanted_profile in item["content_profiles"]
        ]
        provider_order = {item["provider"]: idx for idx, item in enumerate(searchable)}
        provider_labels = {item["provider"]: item.get("name") or item["provider"] for item in providers}

        code_match = _CONTENT_CODE_RE.search(name or "")
        code = code_match.group(1).upper() if code_match else ""
        detail_provider = None
        if code and parsed_profile:
            candidates = [
                item
                for item in providers
                if parsed_profile in (item.get("content_profiles") or [])
                and any("detail" in str(cap).lower() for cap in item.get("capabilities", []))
            ]
            detail_provider = next(
                (item for item in candidates if item["provider"] == parsed_profile),
                candidates[0] if candidates else None,
            )
        preferred = None
        preferred_external = ""
        preferred_image = ""
        reason = ""
        ref_match = _KNOWN_REF_RE.search(name or "")
        if ref_match and ref_match.group(1).lower() in provider_order:
            preferred = ref_match.group(1).lower()
            preferred_external = ref_match.group(2)
            reason = "输入指定来源"
        elif media_info is not None and getattr(media_info, "tmdb_id", None):
            preferred = "tmdb" if "tmdb" in provider_order else None
            preferred_external = str(getattr(media_info, "tmdb_id", "") or "")
            reason = "本地识别命中 TMDB"
        else:
            target = _normalize_title(
                (query or "")
                or (getattr(media_info, "cn_name", None) or getattr(media_info, "title", None))
                or (getattr(media_info, "title_cn", None) or getattr(media_info, "title_en", None))
                if media_info is not None
                else (query or name)
            )
            if target:
                try:
                    subs = [
                        *self._subscribe.get_subscribe_movies(user=user).values(),
                        *self._subscribe.get_subscribe_tvs(user=user).values(),
                    ]
                except Exception:  # noqa: BLE001 - 订阅匹配失败不影响识别
                    subs = []
                for sub in subs:
                    sub_title = _normalize_title(sub.get("name"))
                    if not sub_title or (target not in sub_title and sub_title not in target):
                        continue
                    metadata_ref = str(sub.get("metadata_ref") or "")
                    candidate = metadata_ref.split(":", 1)[0] if ":" in metadata_ref else ""
                    candidate_external = metadata_ref.split(":", 1)[1] if ":" in metadata_ref else ""
                    if candidate in ("", "content_id"):
                        candidate = str(sub.get("anchor_provider") or "")
                        candidate_external = str(sub.get("anchor_external_id") or "")
                    if candidate in provider_order:
                        preferred = candidate
                        preferred_external = candidate_external
                        preferred_image = str(sub.get("image") or "")
                        reason = "命中已有订阅来源"
                        break

        parsed_type = getattr(media_info, "type", MediaType.UNKNOWN) if media_info is not None else MediaType.UNKNOWN
        if not isinstance(parsed_type, MediaType):
            parsed_type = MediaType.from_string(str(parsed_type))
        if parsed_type not in (MediaType.MOVIE, MediaType.TV, MediaType.ANIME):
            parsed_type = MediaType.TV if _EPISODE_RE.search(name or "") else MediaType.MOVIE
        if parsed_type == MediaType.TV:
            media_type = MediaType.TV
        elif parsed_type == MediaType.ANIME:
            media_type = MediaType.ANIME
        else:
            media_type = MediaType.MOVIE
        profile = parsed_profile or ("anime" if parsed_type == MediaType.ANIME else "default")
        title = query or (
            (
                getattr(media_info, "cn_name", None)
                or getattr(media_info, "title", None)
                or getattr(media_info, "title_cn", None)
                or getattr(media_info, "title_en", None)
                or name
            )
            if media_info is not None
            else name
        )

        def search_one(item):
            key = item["provider"]
            try:
                return key, gateway.search(
                    query=str(title),
                    context=context,
                    provider=key,
                    media_type=media_type,
                    content_profile=profile,
                    limit=10 if code else 3,
                )
            except Exception:  # noqa: BLE001 - 单源失败不影响其他源
                return key, []

        def detail_one(item):
            if item is None:
                return None
            try:
                return gateway.lookup(
                    item["provider"],
                    code,
                    context=context,
                    media_type=media_type,
                    scope="release",
                    content_profile=profile,
                )
            except Exception:  # noqa: BLE001 - 聚合详情失败不影响搜索结果
                return None

        matches = []
        detail_record = None
        if searchable or detail_provider:
            executor = ThreadPoolExecutor(max_workers=min(9, len(searchable) + 1))
            search_futures = [executor.submit(search_one, item) for item in searchable]
            detail_future = executor.submit(detail_one, detail_provider) if detail_provider else None
            all_futures = [*search_futures, *([detail_future] if detail_future else [])]
            done, pending = wait(all_futures, timeout=10.0 if detail_provider else 8.0)
            executor.shutdown(wait=False, cancel_futures=True)
            if detail_future is not None and detail_future in done:
                detail_record = detail_future.result()
            for future in done:
                if future is detail_future:
                    continue
                try:
                    key, hits = future.result()
                except Exception:  # noqa: BLE001
                    continue
                for hit in hits or []:
                    ref = hit.get("ref") or {}
                    provider = str(hit.get("provider") or ref.get("provider") or key)
                    external_id = str(ref.get("external_id") or "")
                    if not external_id:
                        continue
                    matches.append(
                        {
                            "provider": provider,
                            "source_label": provider_labels.get(provider, provider),
                            "external_id": external_id,
                            "title": hit.get("title") or "",
                            "year": hit.get("year") or "",
                            "media_type": str(hit.get("media_type") or media_type.value),
                            "content_profile": hit.get("content_profile") or profile,
                            "poster": hit.get("poster") or "",
                            "score": float(hit.get("score") or 0.0),
                            "preferred": provider == preferred
                            and (not preferred_external or external_id == preferred_external),
                            "code_match": bool(
                                code
                                and (
                                    external_id.upper() == code or str(hit.get("title") or "").upper().startswith(code)
                                )
                            ),
                        }
                    )
        if detail_record:
            record_title = str(detail_record.get("title") or "")
            release = str(detail_record.get("release_date") or "")
            images = detail_record.get("images") or {}
            poster_list = images.get("poster") or []
            poster = str(poster_list[0].get("url") or "") if poster_list else ""
            for ref in detail_record.get("refs") or []:
                ref_provider = str(ref.get("provider") or "")
                ref_external = str(ref.get("external_id") or code)
                if not ref_provider or ref_provider in ("content_id", profile):
                    continue
                matches.append(
                    {
                        "provider": ref_provider,
                        "source_label": provider_labels.get(ref_provider, ref_provider.upper()),
                        "external_id": ref_external,
                        "title": record_title,
                        "year": release[:4] if len(release) >= 4 else "",
                        "media_type": "movie",
                        "content_profile": profile,
                        "poster": poster,
                        "score": 100.0,
                        "preferred": ref_provider == preferred
                        and (not preferred_external or ref_external == preferred_external),
                        "code_match": True,
                    }
                )
        deduped = {}
        for match in matches:
            key = match["provider"]
            existing = deduped.get(key)
            if existing is None or match["score"] > existing["score"]:
                deduped[key] = match
        # 优先来源的本地化标题可以不同；其余候选必须与查询标题/编号强相关。
        if preferred and not any(match["provider"] == preferred for match in deduped.values()):
            preferred = None
            reason = ""
        match_target = code or _normalize_title(
            (query or "")
            or (getattr(media_info, "cn_name", None) if media_info is not None else None)
            or (getattr(media_info, "title", None) if media_info is not None else None)
            or (getattr(media_info, "title_cn", None) if media_info is not None else None)
            or (getattr(media_info, "title_en", None) if media_info is not None else None)
            or name
        )
        filtered = []
        for match in deduped.values():
            if code:
                if match.get("code_match"):
                    filtered.append(match)
                continue
            if match.get("preferred") or _title_match_strength(match_target, match.get("title")) >= 0.82:
                filtered.append(match)
        matches = list(filtered)
        global_poster = next(
            (str(item.get("poster") or "") for item in matches if item.get("poster")),
            "",
        )
        poster_fallback = preferred_image or global_poster
        if poster_fallback:
            for item in matches:
                if not item.get("poster"):
                    item["poster"] = poster_fallback
        if preferred and not any(item["preferred"] for item in matches):
            same_provider = [item for item in matches if item["provider"] == preferred]
            if same_provider:
                same_provider[0]["preferred"] = True
        if preferred is None:
            code_hit = next((item for item in matches if item.get("code_match")), None)
            if code_hit is not None:
                preferred = code_hit["provider"]
                reason = "内容标识精确匹配"
                for item in matches:
                    item["preferred"] = item["provider"] == preferred
        matches = sorted(
            matches,
            key=lambda item: (
                not item["preferred"],
                not item.get("code_match", False),
                -item["score"],
                provider_order.get(item["provider"], 999),
                item["title"],
            ),
        )[:12]
        preferred_source = (
            {"provider": preferred, "label": provider_labels.get(preferred, preferred), "reason": reason}
            if preferred
            else None
        )
        return matches, preferred_source

    def search_media_infos(self, keyword, source, page) -> list[dict]:
        """搜索媒体词条"""
        medias = search_media_infos(keyword=keyword, source=source, page=page)
        if not medias and source != "douban":
            # 空结果且 TMDB 搜索出错 → 抛出错误让前端提示"搜索失败"，而非误导性的"未找到相关媒体"
            search_error = self._gw().search_error()
            if search_error:
                raise ServiceError(f"TMDB 搜索请求失败，请稍后重试: {search_error}")
        results = []
        for media in medias:
            d = media.to_dict()
            for img_key in ["image", "poster", "backdrop"]:
                if d.get(img_key):
                    d[img_key] = ImageProxy.get_proxy_image_url(d[img_key], use_proxy=True)
            results.append(d)
        return results

    def get_movie_calendar(self, tid, rssid) -> dict | None:
        """查询电影上映日期"""
        if tid and tid.startswith("DB:"):
            record = self._douban_record(tid.replace("DB:", ""), MediaType.MOVIE)
            if not record:
                return None
            release_date = str(record.get("release_date") or "")
            if not release_date:
                return None
            return {
                "type": MediaType.MOVIE.value,
                "title": record.get("title"),
                "start": release_date,
                "id": tid,
                "year": release_date[0:4] if release_date else "",
                "poster": self._record_poster(record),
                "vote_average": self._record_rating(record) or "无",
                "rssid": rssid,
            }
        else:
            if tid:
                tmdb_info = self._gw().details("tmdb", tid, media_type=MediaType.MOVIE)
            else:
                return None
            if not tmdb_info:
                return None
            poster_path = (
                ImageProxy.get_tmdbimage_url(tmdb_info.get("poster_path")) if tmdb_info.get("poster_path") else ""
            )
            title = tmdb_info.get("title")
            vote_average = tmdb_info.get("vote_average")
            release_date = tmdb_info.get("release_date")
            if not release_date:
                return None
            return {
                "type": MediaType.MOVIE.value,
                "title": title,
                "start": release_date,
                "id": tid,
                "year": release_date[0:4] if release_date else "",
                "poster": poster_path,
                "vote_average": vote_average,
                "rssid": rssid,
            }

    def get_tv_calendar(self, tid, season, name, rssid) -> list | None:
        """查询电视剧上映日期"""
        if tid and tid.startswith("DB:"):
            record = self._douban_record(tid.replace("DB:", ""), MediaType.TV)
            if not record:
                return None
            release_date = str(record.get("release_date") or "")
            if not release_date:
                return None
            return [
                {
                    "type": MediaType.TV.value,
                    "title": record.get("title"),
                    "start": release_date,
                    "id": tid,
                    "year": release_date[0:4] if release_date else "",
                    "poster": self._record_poster(record),
                    "vote_average": self._record_rating(record) or "无",
                    "rssid": rssid,
                }
            ]
        else:
            if tid:
                tmdb_info = self._gw().season_episodes("tmdb", tid, season)
            else:
                return None
            if not tmdb_info:
                return None
            air_date = tmdb_info.get("air_date")
            if not tmdb_info.get("poster_path"):
                tv_tmdb_info = self._gw().details("tmdb", tid, media_type=MediaType.TV)
                if tv_tmdb_info:
                    poster_path = ImageProxy.get_tmdbimage_url(tv_tmdb_info.get("poster_path"))
                else:
                    poster_path = ""
            else:
                poster_path = ImageProxy.get_tmdbimage_url(tmdb_info.get("poster_path"))
            year = air_date[0:4] if air_date else ""
            events = []
            episodes = tmdb_info.get("episodes") or []
            for episode in episodes:
                if season != 1:
                    title = "{} 第{}季第{}集".format(name, season, episode.get("episode_number"))
                else:
                    title = "{} 第{}集".format(name, episode.get("episode_number"))
                events.append(
                    {
                        "type": MediaType.TV.value,
                        "title": title,
                        "start": episode.get("air_date"),
                        "id": tid,
                        "year": year,
                        "poster": poster_path,
                        "vote_average": episode.get("vote_average") or "无",
                        "rssid": rssid,
                    }
                )
            return events

    def get_media_detail(self, tmdbid, mtype_str) -> dict[str, Any] | None:
        """获取媒体详情"""
        mtype = media_type_registry.resolve(mtype_str).legacy_type
        media_info = get_mediainfo_from_id(mtype=mtype, mediaid=tmdbid)
        if not media_info or not media_info.provider_data:
            return None
        fav, rssid, item_url = check_media_exists(
            media_server=self._media_server,
            subscribe=self._subscribe,
            mtype=mtype,
            title=media_info.title,
            year=media_info.year,
            mediaid=media_info.tmdb_id,
        )
        seasons = self._gw().season_summaries(media_info.provider_data)
        sub_seasons: list[int] = []
        if mtype == MediaType.TV:
            try:
                sub_seasons = self._subscribe.get_subscribe_seasons(
                    tmdbid=media_info.tmdb_id,
                    title=media_info.title,
                    year=media_info.year,
                )
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as e:
                log.error(f"[MediaService]查询已订阅季失败: {str(e)}")
        if seasons:
            for season in seasons:
                try:
                    exists = self._media_server.check_item_exists(
                        mtype=mtype,
                        title=media_info.title,
                        year=media_info.year,
                        tmdbid=media_info.tmdb_id,
                        season=season.get("season_number"),
                        content_profile=media_info.content_profile,
                    )
                    season.update({"state": bool(exists)})
                except (ServiceError, RepositoryError, DomainError):
                    raise
                except Exception as e:
                    log.error(f"[MediaService]检查季存在状态失败: {str(e)}")
                    season.update({"state": False})
        poster_image = media_info.get_poster_image()
        if poster_image:
            poster_image = ImageProxy.get_proxy_image_url(
                poster_image, use_proxy=settings.get("app").get("enable_image_proxy", True)
            )
        extras = self._gw().media_extras(media_info)
        return {
            "tmdbid": media_info.tmdb_id,
            "douban_id": media_info.douban_id,
            "type": mtype.value,
            "background": extras.get("background") or [],
            "image": poster_image,
            "vote": media_info.vote_average,
            "year": media_info.year,
            "title": media_info.title,
            "genres": extras.get("genres") or [],
            "overview": media_info.overview,
            "runtime": StringUtils.str_timehours(media_info.runtime),
            "fact": extras.get("fact") or "",
            "crews": extras.get("crews") or [],
            "actors": extras.get("actors") or [],
            "link": media_info.get_detail_url(),
            "douban_link": media_info.get_douban_detail_url(),
            "fav": fav,
            "item_url": item_url,
            "rssid": rssid,
            "seasons": seasons,
            "sub_seasons": sub_seasons,
        }
