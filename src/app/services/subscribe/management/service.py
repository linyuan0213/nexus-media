"""Subscribe service - 订阅业务 Facade."""

import datetime
import re
import time
from datetime import timedelta
from typing import Any

import log
from app.db.repositories.rbac.rbac_user_repo_adapter import RBACUserRepositoryAdapter
from app.db.repositories.transfer_repository import TransferRepository
from app.domain.entities.rss import SubscribeState
from app.domain.enums import SystemConfigKey
from app.domain.lifecycle import LifecycleStatus
from app.domain.media_types import ProviderMediaType
from app.media import MediaInfo
from app.services.lifecycle_service import LifecycleProjector
from app.services.subscribe.management.add_service import SubscribeAddService
from app.services.subscribe.management.finish_service import SubscribeFinishService
from app.services.subscribe.management.query_service import SubscribeQueryService, _normalized_anchor
from app.services.subscribe.management.refresh_service import SubscribeRefreshService
from app.services.subscribe.management.update_service import SubscribeUpdateService
from app.services.subscribe.management.utils import tv_filter_signature
from app.services.web.utils import WebUtils

_ALIAS_MAP_TTL = 1800
_ALIAS_MAP_CACHE: dict[str, tuple[float, dict[str, int]]] = {}


def _norm_title(value) -> str:
    """标题归一化：去空白/常见标点并小写，便于别名比对."""
    return re.sub(r"""[\s~～\-—–:：·・,，.。!！?？'"“”()（）\[\]【】]""", "", str(value or "")).lower()


def _parse_season_number(value) -> int:
    """兼容 SEASON 存 "S02"/"Season 2"/2 等格式."""
    if isinstance(value, int):
        return value
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 1


class SubscribeService:
    """订阅业务 Facade — 订阅的添加、完成、更新、查询、状态变更."""

    def __init__(
        self,
        movie_repo: Any,
        tv_repo: Any,
        tv_episode_repo: Any,
        history_repo: Any,
        message: Any,
        media_service: Any,
        downloader: Any,
        sites: Any,
        indexer_service: Any,
        filter_service: Any,
        event_bus: Any,
        system_config: Any,
        download_repo: Any = None,
        transfer_history_manager: Any = None,
        user_repo: Any = None,
        metadata_gateway: Any = None,
    ):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._tv_episode_repo = tv_episode_repo
        self._history_repo = history_repo
        self._message = message
        self._media = media_service
        self._metadata_gateway = metadata_gateway
        self._downloader = downloader
        self._sites = sites
        self._indexer_service = indexer_service
        self._filter = filter_service
        self._event_bus = event_bus
        self._system_config = system_config
        self._download_repo = download_repo
        self._transfer_history_manager = transfer_history_manager

        self._web_utils = WebUtils(metadata_gateway=metadata_gateway)

        self._update_svc = SubscribeUpdateService(
            self._movie_repo,
            self._tv_repo,
            self._media,
            self._message,
            self._event_bus,
            self._system_config,
            self._web_utils,
            metadata_gateway=metadata_gateway,
        )
        self._add_svc = SubscribeAddService(
            self._movie_repo,
            self._tv_repo,
            self._media,
            self._message,
            self._event_bus,
            self._system_config,
            self._web_utils,
            self._download_repo,
            self._transfer_history_manager,
            self._sites,
            self._indexer_service,
            metadata_gateway=metadata_gateway,
        )
        self._finish_svc = SubscribeFinishService(
            self._movie_repo, self._tv_repo, self._history_repo, self._message, self._event_bus, self._download_repo
        )
        if user_repo is None:
            user_repo = RBACUserRepositoryAdapter()
        self._user_repo = user_repo
        self._query_svc = SubscribeQueryService(
            self._movie_repo,
            self._tv_repo,
            self._tv_episode_repo,
            self._history_repo,
            self._sites,
            self._indexer_service,
            user_repo,
            metadata_gateway=metadata_gateway,
        )
        self._refresh_svc = SubscribeRefreshService(
            self._movie_repo,
            self._tv_repo,
            self._tv_episode_repo,
            self._media,
            metadata_gateway=metadata_gateway,
        )

    @property
    def default_subscribe_setting_tv(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultSubscribeSettingTV) or {}

    @property
    def default_subscribe_setting_mov(self) -> dict | None:
        return self._system_config.get(SystemConfigKey.DefaultSubscribeSettingMovie) or {}

    def update_rss_subscribe(self, *args, **kwargs):
        return self._update_svc.update_rss_subscribe(*args, **kwargs)

    def add_rss_subscribe(self, *args, **kwargs):
        # 插件/系统创建订阅未带用户时，归属首个超级管理员，避免订阅用户为空。
        if kwargs.get("user_id") is None:
            admin_ids = self._user_repo.get_user_ids_by_role_code("superadmin")
            if admin_ids:
                kwargs["user_id"] = admin_ids[0]
        return self._add_svc.add_rss_subscribe(*args, **kwargs)

    def finish_rss_subscribe(self, rssid, media):
        return self._finish_svc.finish_rss_subscribe(rssid, media, self.delete_subscribe)

    def finalize_tv_by_rssid(self, rssid, mtype=None):
        """转移确认后按订阅行定稿（无需 media 对象）。"""
        return self._finish_svc.finalize_tv_by_rssid(rssid, mtype, self.delete_subscribe)

    def finalize_movie_by_rssid(self, rssid):
        """转移确认后按订阅行定稿电影订阅。"""
        return self._finish_svc.finalize_movie_by_rssid(rssid, self.delete_subscribe)

    def media_exists(self, media, total_ep=None) -> bool:
        """媒体是否已入库（用于待转移定稿判定）。"""
        try:
            exist_flag, _, _ = self._downloader.check_exists_medias(meta_info=media, total_ep=total_ep)
            if exist_flag:
                return True
            # 动画订阅可能落在 tv/anime 任一库；主路径未命中时互换类型再查一次。
            if media.type in (ProviderMediaType.SERIES, ProviderMediaType.ANIME):
                original = media.type
                media.type = (
                    ProviderMediaType.ANIME if original == ProviderMediaType.SERIES else ProviderMediaType.SERIES
                )
                try:
                    exist_flag, _, _ = self._downloader.check_exists_medias(meta_info=media, total_ep=total_ep)
                    return bool(exist_flag)
                finally:
                    media.type = original
            return False
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Subscribe]媒体入库检查失败: {e!s}")
            return False

    def _pending_stale(
        self,
        tmdb_id,
        cutoff,
        *,
        identity_id: str | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
    ) -> bool:
        """该订阅最近的下载记录是否已早于 cutoff（用于判定待转移是否超时滞留）。"""
        if not self._download_repo:
            return False
        try:
            if tmdb_id:
                rows = self._download_repo.get_by_tmdb(tmdb_id) or []
            elif identity_id or (anchor_provider and anchor_external_id):
                rows = (
                    self._download_repo.get_by_identity(
                        identity_id=identity_id,
                        anchor_provider=anchor_provider,
                        anchor_external_id=anchor_external_id,
                    )
                    or []
                )
            else:
                return False
        except Exception:  # noqa: BLE001
            return False
        if not rows:
            return False  # 无下载记录：保守不处理
        latest = max(rows, key=lambda r: getattr(r, "date", "") or "")
        try:
            dt = datetime.datetime.strptime((getattr(latest, "date", "") or "").strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        return dt < cutoff

    def reconcile_pending_transfers(self, timeout_minutes: int = 180, now=None) -> None:
        """清理“待转移”订阅：已入库则定稿；超时未入库则重开重试，避免永久滞留。

        定稿会删除订阅行，因此残留的 COMPLETED 即“登记后未定稿”的待转移订阅。
        """
        now = now or datetime.datetime.now()
        cutoff = now - datetime.timedelta(minutes=max(int(timeout_minutes), 1))
        for tv in self._tv_repo.get_all(state=SubscribeState.COMPLETED.value) or []:
            try:
                season = _parse_season_number(getattr(tv, "season", 1))
                total = int(getattr(tv, "total", 0) or 0)
                tv_profile = str(getattr(tv, "content_profile", "") or "").strip()
                tv_mtype = ProviderMediaType.ANIME if tv_profile == "anime" else ProviderMediaType.SERIES
                media = MediaInfo(type=tv_mtype, tmdb_id=str(getattr(tv, "tmdb_id", "") or ""))
                media.title = getattr(tv, "name", "") or ""
                media.year = getattr(tv, "year", "") or ""
                media.begin_season = season
                media.total_episodes = total
                tv_provider, tv_external = _normalized_anchor(
                    getattr(tv, "anchor_provider", ""), getattr(tv, "anchor_external_id", "")
                )
                media.content_profile = tv_profile or "default"
                media.anchor_provider = tv_provider
                media.anchor_external_id = tv_external
                media.keyword = getattr(tv, "keyword", None)
                if self.media_exists(media, total_ep={season: total}):
                    self.finalize_tv_by_rssid(tv.id, tv_mtype)
                elif self._pending_stale(getattr(tv, "tmdb_id", ""), cutoff):
                    self.update_rss_state(ProviderMediaType.SERIES, tv.id, SubscribeState.RUNNING.value)
                    log.info(f"[Subscribe]待转移超时，重开订阅 rssid={tv.id}（{media.title}）")
            except Exception as e:  # noqa: BLE001
                log.warn(f"[Subscribe]待转移电视剧清理失败 rssid={getattr(tv, 'id', None)}: {e!s}")
        movies = self._movie_repo.get_all() or []
        pairs: list[tuple[str, str]] = []
        for mv in movies:
            provider, external = _normalized_anchor(
                getattr(mv, "anchor_provider", ""), getattr(mv, "anchor_external_id", "")
            )
            if provider and external:
                pairs.append((provider, external))
        transferred: set[tuple[str, str]] = set()
        transferred_external: set[str] = set()
        if pairs:
            try:
                repo = TransferRepository()
                transferred = repo.get_existing_anchors(list(dict.fromkeys(pairs)))
                transferred_external = repo.get_existing_external_ids([external for _, external in pairs])
            except Exception as e:  # noqa: BLE001
                log.debug(f"[Subscribe]转移历史查询失败: {e!s}")
        for mv in movies:
            try:
                provider, external = _normalized_anchor(
                    getattr(mv, "anchor_provider", ""), getattr(mv, "anchor_external_id", "")
                )
                pair = (provider or "", external or "")
                over_edition = bool(getattr(mv, "over_edition", False))
                # 转移成功即入库；洗版订阅不能因旧转移历史被立即定稿。
                if not over_edition and (pair in transferred or (pair[1] and pair[1] in transferred_external)):
                    self.finalize_movie_by_rssid(mv.id)
                    continue
                state = getattr(mv, "state", None)
                if state not in (None, "", SubscribeState.COMPLETED.value):
                    continue
                media = MediaInfo(type=ProviderMediaType.MOVIE, tmdb_id=str(getattr(mv, "tmdb_id", "") or ""))
                media.title = getattr(mv, "name", "") or ""
                media.year = getattr(mv, "year", "") or ""
                media.content_profile = str(getattr(mv, "content_profile", "") or "default")
                media.anchor_provider = provider
                media.anchor_external_id = external
                media.keyword = getattr(mv, "keyword", None)
                if self.media_exists(media):
                    self.finalize_movie_by_rssid(mv.id)
                elif self._pending_stale(
                    getattr(mv, "tmdb_id", ""),
                    cutoff,
                    identity_id=getattr(mv, "identity_id", None),
                    anchor_provider=provider,
                    anchor_external_id=external,
                ):
                    self.update_rss_state(ProviderMediaType.MOVIE, mv.id, SubscribeState.RUNNING.value)
                    log.info(f"[Subscribe]待转移超时，重开电影订阅 rssid={mv.id}（{media.title}）")
            except Exception as e:  # noqa: BLE001
                log.warn(f"[Subscribe]待转移电影清理失败 rssid={getattr(mv, 'id', None)}: {e!s}")

    def get_subscription_count(self, user=None):
        return self._query_svc.get_subscription_count(user=user)

    def get_subscribe_movies(self, rid=None, state=None, user=None):
        return self._query_svc.get_subscribe_movies(rid, state, user=user)

    def get_subscribe_tvs(self, rid=None, state=None, user=None):
        return self._query_svc.get_subscribe_tvs(rid, state, user=user)

    def get_subscribe_tv_episodes(self, rssid):
        return self._query_svc.get_subscribe_tv_episodes(rssid)

    def get_subscribe_by_anchor(
        self,
        anchor_provider: str | None,
        anchor_external_id: str | None,
        mtype: ProviderMediaType,
        user: Any = None,
    ) -> dict | None:
        return self._query_svc.get_subscribe_by_anchor(anchor_provider, anchor_external_id, mtype, user=user)

    def get_subscribe_seasons(
        self,
        tmdbid=None,
        title=None,
        year=None,
        user=None,
        anchor_provider=None,
        anchor_external_id=None,
    ):
        return self._query_svc.get_subscribe_seasons(
            tmdbid,
            title,
            year,
            user=user,
            anchor_provider=anchor_provider,
            anchor_external_id=anchor_external_id,
        )

    def get_subscribe_id_by_anchor(
        self,
        mtype,
        anchor_provider,
        anchor_external_id,
        season=None,
        user=None,
    ) -> int | None:
        return self._query_svc.get_subscribe_id_by_anchor(
            mtype,
            anchor_provider,
            anchor_external_id,
            season=season,
            user=user,
        )

    def check_history(self, type_str, name, year=None, season=None):
        return self._query_svc.check_history(type_str, name, year, season)

    def cancel_subscribe(
        self,
        mtype,
        title=None,
        year=None,
        season=None,
        rssid=None,
        tmdbid=None,
        user=None,
        reason: str = "user_removed",
    ):
        """用户取消订阅：先快照订阅行，删除成功后投影 cancel 事件."""
        rows = self._subscription_snapshot(mtype, rssid, title, year, season, tmdbid, user)
        deleted = self.delete_subscribe(mtype, title, year, season, rssid, tmdbid, user=user)
        if deleted:
            self._record_cancelled(rows, reason)
        return deleted

    def _subscription_snapshot(self, mtype, rssid, title, year, season, tmdbid, user) -> list[dict]:
        data: dict = {}
        if not rssid:
            rssid = self.get_subscribe_id(
                mtype,
                title or "",
                year,
                season,
                tmdbid,
                user_id=user.user_id if user is not None else None,
            )
        if not rssid:
            return []
        if mtype == ProviderMediaType.MOVIE:
            data = self.get_subscribe_movies(rid=int(rssid), user=user)
        else:
            data = self.get_subscribe_tvs(rid=int(rssid), user=user)
        return list((data or {}).values())

    @staticmethod
    def _record_cancelled(rows: list[dict], reason: str) -> None:
        if not rows:
            return
        projector = LifecycleProjector()
        for row in rows:
            identity_id = str(row.get("identity_id") or "")
            if not identity_id:
                continue
            media_type = str(row.get("type") or "")
            season = _parse_season_number(row.get("season")) if media_type in {"tv", "anime"} else 0
            projector.record_subscription_outcome(
                identity_id=identity_id,
                series_key=row.get("series_key"),
                status=LifecycleStatus.CANCELLED,
                event_type="subscribe.cancelled",
                media_type=media_type or "movie",
                season=season,
                title=row.get("name"),
                year=row.get("year"),
                poster=row.get("poster") or row.get("image"),
                source_provider=row.get("anchor_provider") or row.get("provider"),
                content_profile=row.get("content_profile"),
                user_id=row.get("user_id"),
                message="订阅已取消",
                payload={"source": "SUBSCRIBE", "rssid": row.get("id"), "reason": reason},
                event_key=f"subscribe-cancelled:{row.get('id')}",
            )

    def delete_subscribe(self, mtype, title=None, year=None, season=None, rssid=None, tmdbid=None, user=None):
        return self._query_svc.delete_subscribe(mtype, title, year, season, rssid, tmdbid, user=user)

    def get_subscribe_id_by_alias(self, title: str, mtype=None) -> int | None:
        """按 TMDB 别名（正名/原名/译名/别名）匹配订阅 ID.

        用于 BGM/豆瓣等外部榜单名称与订阅名不一致的场景（如 BGM「画完这个再去死」
        对应订阅「描绘直至生命尽头」）。别名映射带 30 分钟缓存。
        """
        norm = _norm_title(title)
        if not norm:
            return None
        for sub_type in (mtype,) if mtype else (ProviderMediaType.SERIES, ProviderMediaType.MOVIE):
            mapping = self._build_alias_map(sub_type)
            rid = mapping.get(norm)
            if rid:
                return rid
            for alias, alias_rid in mapping.items():
                if alias in norm or norm in alias:
                    return alias_rid
        return None

    def _build_alias_map(self, mtype) -> dict[str, int]:
        cache_key = mtype.value if hasattr(mtype, "value") else str(mtype)
        cached = _ALIAS_MAP_CACHE.get(cache_key)
        if cached and cached[0] > time.time():
            return cached[1]
        mapping: dict[str, int] = {}
        subs = self.get_subscribe_movies() if mtype == ProviderMediaType.MOVIE else self.get_subscribe_tvs()
        for rid, info in (subs or {}).items():
            tmdbid = (info or {}).get("tmdbid")
            if not tmdbid or not str(tmdbid).isdigit():
                continue
            try:
                names = (
                    self._metadata_gateway.all_names("tmdb", int(tmdbid), mtype)
                    if self._metadata_gateway is not None
                    else []
                )
            except Exception as e:  # noqa: BLE001
                log.debug(f"[Subscribe]获取 TMDB 别名失败 {tmdbid}: {e!s}")
                continue
            for name in names:
                key = _norm_title(name)
                if key:
                    mapping.setdefault(key, int(rid))
        _ALIAS_MAP_CACHE[cache_key] = (time.time() + _ALIAS_MAP_TTL, mapping)
        return mapping

    def get_history_id(self, mtype, title, year=None, tmdbid=None):
        return self._query_svc.get_history_id(mtype, title, year, tmdbid)

    def get_subscribe_id(
        self,
        mtype,
        title,
        year=None,
        season=None,
        tmdbid=None,
        user_id=None,
        content_profile=None,
    ):
        return self._query_svc.get_subscribe_id(
            mtype,
            title,
            year,
            season,
            tmdbid,
            user_id=user_id,
            content_profile=content_profile,
        )

    def refresh_rss_metainfo(self):
        return self._refresh_svc.refresh_rss_metainfo(self.get_subscribe_movies, self.get_subscribe_tvs)

    def reset_stale_searching(self, timeout_minutes: int = 90) -> int:
        """SEARCHING 看门狗：超时未推进的订阅回到 ERROR，等待下一轮重试."""
        cutoff = (datetime.datetime.now() - timedelta(minutes=max(1, int(timeout_minutes)))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return self._movie_repo.reset_stale_searching(cutoff)

    def update_rss_state(self, rtype, rssid, state):
        if rtype == ProviderMediaType.MOVIE:
            movies = self._movie_repo.get_all(rssid=rssid)
            if not movies:
                return
            entity = movies[0]
            if state == SubscribeState.RUNNING.value:
                entity.mark_running()
            elif state == SubscribeState.COMPLETED.value:
                entity.mark_completed()
            elif state == SubscribeState.CANCELLED.value:
                entity.mark_cancelled()
            elif state == SubscribeState.PENDING.value:
                entity.state = SubscribeState.PENDING.value
            elif state == SubscribeState.ERROR.value:
                entity.state = SubscribeState.ERROR.value
            self._movie_repo.update(rssid=rssid, state=entity.state)
        else:
            tvs = self._tv_repo.get_all(rssid=rssid)
            if not tvs:
                return
            entity = tvs[0]
            if state == SubscribeState.RUNNING.value:
                entity.mark_running()
            elif state == SubscribeState.COMPLETED.value:
                entity.mark_completed()
            elif state == SubscribeState.CANCELLED.value:
                entity.mark_cancelled()
            elif state == SubscribeState.PENDING.value:
                entity.state = SubscribeState.PENDING.value
            elif state == SubscribeState.ERROR.value:
                entity.state = SubscribeState.ERROR.value
            self._tv_repo.update(rssid=rssid, state=entity.state)

    def update_subscribe_over_edition(self, rtype, rssid, media):
        if not rssid or not media.res_order or not media.filter_rule:
            return False
        if rtype == ProviderMediaType.MOVIE:
            self._movie_repo.update_filter_order(rssid=rssid, res_order=media.res_order)
        else:
            self._tv_repo.update_filter_order(rssid=rssid, res_order=media.res_order)
        over_edition_order = self._filter.get_rule_first_order(rulegroup=media.filter_rule)
        if int(media.res_order) >= int(over_edition_order):
            if rtype == ProviderMediaType.MOVIE:
                # 电影洗版同样只登记待转移，入库确认后再定稿删除订阅
                self.update_rss_state(rtype=rtype, rssid=rssid, state=SubscribeState.COMPLETED.value)
            else:
                self.finish_rss_subscribe(rssid=rssid, media=media)
            return True
        else:
            self.update_rss_state(rtype=rtype, rssid=rssid, state=SubscribeState.RUNNING.value)
        return False

    def check_subscribe_over_edition(self, rtype, rssid, res_order):
        if rtype == ProviderMediaType.MOVIE:
            pre_res_order = self._movie_repo.get_filter_order(rssid=rssid)
        else:
            pre_res_order = self._tv_repo.get_filter_order(rssid=rssid)
        if not pre_res_order:
            return True
        return int(pre_res_order) < int(res_order or 0)

    def _find_tv_siblings(self, rssid, media_info) -> list:
        """同媒体（TMDB+季）其他用户的订阅（排除主订阅、洗版、过滤要求不同者）"""
        tmdb = str(getattr(media_info, "tmdb_id", "") or "")
        season = media_info.get_season_string() if hasattr(media_info, "get_season_string") else ""
        primary = self._tv_repo.get_all(rssid=rssid)
        primary_sig = tv_filter_signature(primary[0]) if primary else None
        siblings = []
        for row in self._tv_repo.get_all() or []:
            rid = getattr(row, "id", None)
            if rid is None or rid == rssid:
                continue
            if str(getattr(row, "tmdb_id", "") or "") != tmdb:
                continue
            if season and str(getattr(row, "season", "") or "") != str(season):
                continue
            if getattr(row, "over_edition", False):
                continue
            if primary_sig is not None and tv_filter_signature(row) != primary_sig:
                continue
            siblings.append(row)
        return siblings

    def clear_subscribe_tv_lack(self, rssid, media_info=None) -> None:
        """整季已全部拿到时清空缺失集，避免状态回退后按旧缺集重复下载."""
        targets = [rssid]
        if media_info is not None:
            for sibling in self._find_tv_siblings(rssid, media_info):
                targets.append(getattr(sibling, "id", None))
        for target in targets:
            if target:
                self._tv_repo.update_lack(title=None, year=None, season=None, rssid=target, lack_episodes=[])

    def update_subscribe_tv_lack(self, rssid, media_info, seasoninfo):
        self._apply_tv_lack(rssid, media_info, seasoninfo)
        # 同媒体其他用户订阅联动更新缺集进度（ADR-021 5.4）
        for sibling in self._find_tv_siblings(rssid, media_info):
            self._apply_tv_lack(getattr(sibling, "id", None), media_info, seasoninfo)

    def _apply_tv_lack(self, rssid, media_info, seasoninfo):
        if not rssid:
            return
        self._tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state=SubscribeState.RUNNING.value)
        if not seasoninfo:
            return
        for info in seasoninfo:
            if str(info.get("season")) == media_info.get_season_seq():
                if info.get("episodes"):
                    log.info(
                        "[Subscribe]更新电视剧 {} {} 缺失集数为 {}".format(
                            media_info.get_title_string(), media_info.get_season_string(), len(info.get("episodes"))
                        )
                    )
                    self._tv_repo.update_lack(
                        title=None, year=None, season=None, rssid=rssid, lack_episodes=info.get("episodes")
                    )
                break

    def truncate_rss_episodes(self):
        self._tv_episode_repo.delete_all()
