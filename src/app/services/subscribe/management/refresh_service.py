"""Subscribe refresh service - 按统一身份刷新订阅元数据."""

import log
from app.core.settings import settings
from app.db.transaction import transaction_scope
from app.domain.entities.rss import SubscribeState
from app.domain.mediatypes import MediaType
from app.media import meta_info
from app.media.metadata.gateway import MetadataContext, MetadataGateway
from app.services.subscribe.management.utils import gen_rss_note


class SubscribeRefreshService:
    """刷新订阅服务"""

    _metadata_gateway: MetadataGateway | None = None

    def __init__(
        self,
        movie_repo,
        tv_repo,
        tv_episode_repo,
        media_service,
        metadata_gateway: MetadataGateway | None = None,
    ):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._tv_episode_repo = tv_episode_repo
        self._media = media_service
        self._metadata_gateway = metadata_gateway

    def refresh_rss_metainfo(self, get_subscribe_movies_fn, get_subscribe_tvs_fn) -> None:
        legacy_fallback = bool((settings.get("media") or {}).get("legacy_tmdb_fallback", True))
        """定时将豆瓣订阅转换为TMDB的订阅，并更新订阅的TMDB信息"""
        log.info("[Subscribe]开始刷新订阅TMDB信息...")
        rss_movies = get_subscribe_movies_fn(state=SubscribeState.RUNNING.value)
        for _rid, rss_info in rss_movies.items():
            if rss_info.get("fuzzy_match"):
                continue
            anchor_provider = str(rss_info.get("anchor_provider") or "")
            if anchor_provider and self._refresh_anchor_movie(rss_info):
                continue
            if anchor_provider and anchor_provider != "tmdb":
                # 无法从统一身份拿到快照时，不回退为 TMDB 桥接
                continue
            if not legacy_fallback and not anchor_provider:
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            if tmdbid:
                log.debug(f"[Subscribe]{MediaType.MOVIE.display_name} {name} 已有 TMDB ID {tmdbid}，跳过刷新")
                continue
            media_info = self.__get_media_info(tmdbid=tmdbid, name=name, year=year, mtype=MediaType.MOVIE, cache=True)
            if media_info and media_info.tmdb_id and media_info.title != name:
                log.info(
                    f"[Subscribe]检测到TMDB信息变化，"
                    f"更新{MediaType.MOVIE.display_name}订阅 {name} 为 {media_info.title}"
                )
                self._movie_repo.update_tmdb(
                    rid=rssid,
                    tmdbid=str(media_info.tmdb_id or ""),
                    title=media_info.title or "",
                    year=media_info.year or "",
                    image=media_info.get_poster_image(),
                    desc=media_info.overview or "",
                    note=gen_rss_note(media_info),
                )

        rss_tvs = get_subscribe_tvs_fn(state=SubscribeState.RUNNING.value)
        for rss_info in rss_tvs.values():
            if rss_info.get("fuzzy_match"):
                continue
            anchor_provider = str(rss_info.get("anchor_provider") or "")
            if anchor_provider and self._refresh_anchor_tv(rss_info):
                continue
            if anchor_provider and anchor_provider != "tmdb":
                # 无法从统一身份拿到快照时，不回退为 TMDB 桥接
                continue
            if not legacy_fallback and not anchor_provider:
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            season = rss_info.get("season") or 1
            total = rss_info.get("total")
            total_ep = rss_info.get("total_ep")
            lack = rss_info.get("lack")
            if tmdbid:
                log.debug(f"[Subscribe]{MediaType.TV.display_name} {name} 已有 TMDB ID {tmdbid}，跳过刷新")
                continue
            media_info = self.__get_media_info(tmdbid=tmdbid, name=name, year=year, mtype=MediaType.TV, cache=True)
            if media_info and media_info.tmdb_id:
                total_episode = self._season_episode_count(
                    media_info=media_info,
                    title=str(name or media_info.title or ""),
                    year=str(media_info.year or year or "") or None,
                    media_type=MediaType.TV,
                    season=int(str(season).replace("S", "")),
                    content_profile="default",
                )
                if total_ep:
                    total_episode = total_ep
                if total_episode and (name != media_info.title or total != total_episode):
                    lack_episode = total_episode - (total - lack)
                    log.info(
                        f"[Subscribe]检测到TMDB信息变化，"
                        f"更新{MediaType.TV.display_name}订阅 {name} 为 {media_info.title}，"
                        f"总集数为：{total_episode}"
                    )
                    # TV 订阅需同时更新 tv_repo + tv_episode_repo，使用事务保证原子性
                    with transaction_scope():
                        self._tv_repo.update_tmdb(
                            rid=rssid,
                            tmdbid=str(media_info.tmdb_id or ""),
                            title=media_info.title or "",
                            year=media_info.year or "",
                            total=total_episode,
                            lack=lack_episode,
                            image=media_info.get_poster_image(),
                            desc=media_info.overview or "",
                            note=gen_rss_note(media_info),
                        )
                        self._tv_episode_repo.update(
                            rid=rssid, episodes=list(range(total_episode - lack_episode + 1, total_episode + 1))
                        )
        log.info("[Subscribe]订阅TMDB信息刷新完成")

    @staticmethod
    def _snapshot_value(snapshot: dict, name: str):
        item = (snapshot.get("fields") or {}).get(name)
        if isinstance(item, dict):
            return item.get("value")
        return item

    @staticmethod
    def _snapshot_poster(snapshot: dict) -> str:
        images = snapshot.get("images") or {}
        for key in ("poster", "thumb", "cover"):
            values = images.get(key) or []
            for item in values:
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])
        return ""

    @staticmethod
    def _snapshot_tmdb_id(snapshot: dict) -> str:
        for ref in snapshot.get("refs") or []:
            if isinstance(ref, dict) and ref.get("provider") == "tmdb":
                return str(ref.get("external_id") or "")
        return ""

    def _snapshot_for(self, rss_info: dict, media_type: MediaType) -> dict | None:
        if self._metadata_gateway is None:
            return None
        provider = str(rss_info.get("anchor_provider") or "").strip()
        external = str(rss_info.get("anchor_external_id") or "").strip()
        if not provider or not external:
            return None
        content_profile = str(rss_info.get("content_profile") or "default")
        try:
            envelope = self._metadata_gateway.resolve(
                provider,
                external,
                context=MetadataContext(
                    user_id=rss_info.get("user_id"),
                    purpose="subscribe.refresh",
                    allow_private=True,
                    content_profile=content_profile,
                ),
                media_type=media_type,
                max_age_seconds=300,
            )
            return envelope.metadata if envelope is not None else None
        except Exception as exc:  # noqa: BLE001
            log.debug(f"[Subscribe]统一身份刷新失败 {provider}:{external}: {exc}")
            return None

    def _scope_kwargs(self, rss_info: dict, snapshot: dict) -> dict:
        return {
            "identity_id": snapshot.get("identity_id") or rss_info.get("identity_id"),
            "anchor_provider": rss_info.get("anchor_provider"),
            "anchor_external_id": rss_info.get("anchor_external_id"),
            "content_profile": snapshot.get("content_profile") or rss_info.get("content_profile"),
            "metadata_policy": rss_info.get("metadata_policy"),
            "naming_profile": rss_info.get("naming_profile"),
        }

    def _refresh_anchor_movie(self, rss_info: dict) -> bool:
        snapshot = self._snapshot_for(rss_info, MediaType.MOVIE)
        if not snapshot:
            return False
        title = str(self._snapshot_value(snapshot, "title") or rss_info.get("name") or "")
        year = str(self._snapshot_value(snapshot, "year") or rss_info.get("year") or "")
        overview = str(self._snapshot_value(snapshot, "overview") or "")
        poster = self._snapshot_poster(snapshot)
        tmdb_id = self._snapshot_tmdb_id(snapshot)
        media_info = meta_info(title=f"{title} {year}".strip())
        media_info.title = title
        media_info.year = year
        media_info.type = MediaType.MOVIE
        media_info.poster_path = poster
        media_info.overview = overview
        media_info.release_date = str(self._snapshot_value(snapshot, "release_date") or "")
        try:
            media_info.vote_average = float(self._snapshot_value(snapshot, "vote_average") or 0)
        except (TypeError, ValueError):
            media_info.vote_average = 0.0
        media_info.anchor_provider = rss_info.get("anchor_provider")
        media_info.anchor_external_id = rss_info.get("anchor_external_id")
        media_info.identity_id = snapshot.get("identity_id")
        media_info.content_profile = snapshot.get("content_profile") or "default"
        self._movie_repo.update(
            rss_info.get("id"),
            name=title,
            year=year,
            tmdbid=tmdb_id or None,
            image=poster,
            desc=overview,
            note=gen_rss_note(media_info),
            **self._scope_kwargs(rss_info, snapshot),
        )
        return True

    def _refresh_anchor_tv(self, rss_info: dict) -> bool:
        snapshot = self._snapshot_for(rss_info, MediaType.TV)
        if not snapshot:
            return False
        title = str(self._snapshot_value(snapshot, "title") or rss_info.get("name") or "")
        year = str(self._snapshot_value(snapshot, "year") or rss_info.get("year") or "")
        overview = str(self._snapshot_value(snapshot, "overview") or "")
        poster = self._snapshot_poster(snapshot)
        tmdb_id = self._snapshot_tmdb_id(snapshot)
        season = int(str(rss_info.get("season") or 1).replace("S", ""))
        total_episode = 0
        for item in snapshot.get("seasons") or []:
            if isinstance(item, dict) and int(item.get("season_number") or -1) == season:
                total_episode = int(item.get("episode_count") or 0)
                break
        total_ep = rss_info.get("total_ep")
        if total_ep:
            total_episode = int(total_ep)
        total = int(rss_info.get("total") or 0)
        lack = int(rss_info.get("lack") or 0)
        media_info = meta_info(title=f"{title} {year}".strip())
        media_info.title = title
        media_info.year = year
        media_info.type = MediaType.TV
        media_info.poster_path = poster
        media_info.overview = overview
        media_info.release_date = str(self._snapshot_value(snapshot, "first_air_date") or "")
        try:
            media_info.vote_average = float(self._snapshot_value(snapshot, "vote_average") or 0)
        except (TypeError, ValueError):
            media_info.vote_average = 0.0
        media_info.anchor_provider = rss_info.get("anchor_provider")
        media_info.anchor_external_id = rss_info.get("anchor_external_id")
        media_info.identity_id = snapshot.get("identity_id")
        media_info.content_profile = snapshot.get("content_profile") or "default"
        updates = {
            "name": title,
            "year": year,
            "tmdbid": tmdb_id or None,
            "image": poster,
            "desc": overview,
            "note": gen_rss_note(media_info),
            **self._scope_kwargs(rss_info, snapshot),
        }
        if total_episode:
            lack_episode = max(total_episode - max(total - lack, 0), 0)
            updates.update({"total": total_episode, "lack": lack_episode})
            with transaction_scope():
                self._tv_repo.update(rss_info.get("id"), **updates)
                self._tv_episode_repo.update(
                    rid=rss_info.get("id"),
                    episodes=list(range(total_episode - lack_episode + 1, total_episode + 1)),
                )
        else:
            self._tv_repo.update(rss_info.get("id"), **updates)
        return True

    def _season_episode_count(
        self,
        *,
        media_info,
        title: str,
        year: str | None,
        media_type: MediaType,
        season: int,
        content_profile: str,
    ) -> int:
        if self._metadata_gateway is None:
            return 0
        return self._metadata_gateway.resolve_season_episode_count(
            context=MetadataContext(
                content_profile=content_profile,
                purpose="subscribe.refresh",
                allow_private=True,
            ),
            provider="tmdb",
            external_id=str(getattr(media_info, "tmdb_id", "") or ""),
            title=title,
            year=year,
            media_type=media_type,
            season=season,
            content_profile=content_profile,
            provider_data=getattr(media_info, "provider_data", None),
        )

    def __get_media_info(self, tmdbid, name, year, mtype, cache=True):
        """综合返回媒体信息"""
        if self._metadata_gateway is None:
            log.warn("[Subscribe]元数据网关不可用，跳过刷新媒体信息")
            return None
        if tmdbid and not str(tmdbid).startswith("DB:"):
            media_info = meta_info(title=("%s %s" % (name, year)).strip())
            tmdb_info = self._metadata_gateway.details("tmdb", tmdbid, media_type=mtype)
            media_info.set_provider_data(tmdb_info)
        else:
            media_info = self._metadata_gateway.resolve_by_title(
                title=f"{name} {year}".strip(),
                media_type=mtype,
                year=str(year or "") or None,
                strict=True,
                cache=cache,
                context=MetadataContext(
                    content_profile="default",
                    purpose="subscribe.refresh",
                    allow_private=True,
                ),
            )
        return media_info

    def refresh_rss_metainfo_cached(self, get_subscribe_movies_fn, get_subscribe_tvs_fn) -> None:
        """带缓存的刷新入口：同一次调度中避免重复请求同一 tmdbid/name/year 组合."""
        self.__cache = {}
        self.__orig_get_media_info = self.__get_media_info
        self.__get_media_info = self.__get_media_info_cached
        try:
            self.refresh_rss_metainfo(get_subscribe_movies_fn, get_subscribe_tvs_fn)
        finally:
            self.__get_media_info = self.__orig_get_media_info
            del self.__orig_get_media_info
            self.__cache.clear()

    def __get_media_info_cached(self, tmdbid, name, year, mtype, cache=True):
        """内部缓存版本，供 refresh_rss_metainfo_cached 使用."""
        key = (str(tmdbid) if tmdbid else "", name, year, str(mtype))
        if key not in self.__cache:
            self.__cache[key] = self.__orig_get_media_info(tmdbid, name, year, mtype, cache)
        return self.__cache[key]
