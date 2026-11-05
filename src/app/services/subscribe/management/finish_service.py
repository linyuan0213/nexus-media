"""Subscribe finish service - 完成订阅."""

import re
from typing import Any

import log
from app.domain.lifecycle import LifecycleStatus
from app.domain.media_type_utils import MediaTypeMapper
from app.domain.mediatypes import MediaType
from app.events import Event
from app.events.constants import SUBSCRIBE_FINISHED
from app.events.payloads import SubscribeFinishedPayload
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.media import MediaInfo
from app.services.lifecycle_service import LifecycleProjector
from app.services.subscribe.management.utils import tv_filter_signature


def _row_ref(row: Any) -> str:
    metadata_ref = str(getattr(row, "METADATA_REF", "") or "").strip()
    if metadata_ref:
        return metadata_ref
    identity_id = str(getattr(row, "IDENTITY_ID", "") or "").strip()
    if identity_id:
        return f"id:{identity_id}"
    provider = str(getattr(row, "ANCHOR_PROVIDER", "") or "").strip().lower()
    external = str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "").strip()
    if provider and external:
        return f"{provider}:{external}"
    tmdb = str(getattr(row, "TMDBID", "") or "").strip()
    return f"tmdb:{tmdb}" if tmdb.isdigit() else ""


def _history_scope(row: Any) -> dict[str, Any]:
    return {
        "anchor_provider": getattr(row, "ANCHOR_PROVIDER", None),
        "anchor_external_id": getattr(row, "ANCHOR_EXTERNAL_ID", None),
        "identity_id": getattr(row, "IDENTITY_ID", None),
        "content_profile": getattr(row, "CONTENT_PROFILE", None),
        "provider": getattr(row, "PROVIDER", None),
        "metadata_ref": getattr(row, "METADATA_REF", None),
        "metadata_policy": getattr(row, "METADATA_POLICY", None),
        "naming_profile": getattr(row, "NAMING_PROFILE", None),
    }


def _record_subscription_completed(row: Any, rssid: int, media_type: str = "tv") -> None:
    identity_id = str(getattr(row, "IDENTITY_ID", "") or "")
    if not identity_id:
        return
    profile = str(getattr(row, "CONTENT_PROFILE", "") or "default")
    if profile == "anime":
        media_type = "anime"
    match = re.search(r"\d+", str(getattr(row, "SEASON", "") or ""))
    season = int(match.group()) if match else 0
    try:
        LifecycleProjector().record_subscription_outcome(
            identity_id=identity_id,
            series_key=getattr(row, "SERIES_KEY", None),
            status=LifecycleStatus.SUCCEEDED,
            event_type="subscribe.completed",
            media_type=media_type,
            season=season,
            title=getattr(row, "NAME", None),
            year=getattr(row, "YEAR", None),
            poster=getattr(row, "IMAGE", None),
            source_provider=getattr(row, "ANCHOR_PROVIDER", None) or getattr(row, "PROVIDER", None),
            content_profile=profile,
            user_id=getattr(row, "USER_ID", None),
            message="订阅已完成",
            payload={"source": "SUBSCRIBE", "rssid": rssid},
            event_key=f"subscribe-completed:{rssid}",
        )
    except Exception as exc:  # noqa: BLE001 - 事件写入失败不应阻断完成流程
        log.warn(f"[Subscribe]记录订阅完成事件失败 rssid={rssid}: {exc}")


class SubscribeFinishService:
    """完成订阅服务"""

    def __init__(self, movie_repo, tv_repo, history_repo, message, event_bus, download_repo=None):
        self._movie_repo = movie_repo
        self._tv_repo = tv_repo
        self._history_repo = history_repo
        self._message = message
        self._event_bus = event_bus
        self._download_repo = download_repo

    def _finish_sibling_tvs(self, primary_row, media: Any, delete_subscribe_fn) -> None:
        """同媒体其他用户的订阅联动完成（共享媒体库已满足，ADR-021 5.4）"""
        try:
            siblings = self._tv_repo.get_all() or []
        except Exception as e:  # noqa: BLE001
            log.debug(f"[Subscribe]查询兄弟订阅失败: {e}")
            return
        primary_ref = _row_ref(primary_row)
        season = str(getattr(primary_row, "SEASON", None) or getattr(primary_row, "season", "") or "")
        primary_sig = tv_filter_signature(primary_row)
        for row in siblings:
            sid = getattr(row, "ID", None) or getattr(row, "id", None)
            if not sid or str(sid) == str(getattr(primary_row, "ID", "") or getattr(primary_row, "id", "")):
                continue
            row_ref = _row_ref(row)
            row_season = str(getattr(row, "SEASON", None) or getattr(row, "season", "") or "")
            if row_ref != primary_ref or (season and row_season != season):
                continue
            if getattr(row, "OVER_EDITION", None) or getattr(row, "over_edition", False):
                continue
            if tv_filter_signature(row) != primary_sig:
                continue
            log.info(f"[Subscribe]联动完成兄弟订阅 rssid={sid}（同一媒体共享下载）")
            _record_subscription_completed(row, int(sid), "tv")
            delete_subscribe_fn(mtype=MediaType.TV, rssid=sid)

    def finish_rss_subscribe(self, rssid: int | None, media: Any, delete_subscribe_fn) -> None:
        """完成订阅"""
        if not rssid or not media:
            return
        rtype = MediaTypeMapper.to_tmdb(media.type)
        over_edition = False
        if media.type == MediaType.MOVIE:
            rss = self._movie_repo.get_all(rssid=rssid)
            if not rss:
                return
            row = rss[0]
            owner_user_id = getattr(row, "USER_ID", None)
            # 删除订阅前先固化海报/画像/归属，后续通知与历史不再依赖订阅行。
            image = str(getattr(row, "IMAGE", "") or "")
            if image and not str(getattr(media, "poster_path", "") or ""):
                media.poster_path = image
            media.user_id = owner_user_id
            current_profile = str(getattr(media, "content_profile", "") or "")
            if not current_profile or current_profile == "default":
                media.content_profile = str(getattr(row, "CONTENT_PROFILE", None) or "default")
            self._history_repo.upsert(
                rssid=rssid,
                rtype=rtype,
                name=row.NAME,
                year=row.YEAR,
                tmdbid=row.TMDBID if _row_ref(row).startswith("tmdb:") else "",
                image=media.get_poster_image() or image,
                desc=media.overview,
                user_id=owner_user_id,
                **_history_scope(row),
            )
            _record_subscription_completed(row, rssid, "movie")
            delete_subscribe_fn(mtype=MediaType.MOVIE, rssid=rssid)
        else:
            rss = self._tv_repo.get_all(rssid=rssid)
            if not rss:
                return
            row = rss[0]
            # TOTAL = 该季总集数（新增时由 TMDB/用户总集数写入，恒有值）；
            # TOTAL_EP 是"用户填写的总集数"可空字段，不能作为历史展示来源，
            # 否则历史卡片会显示"共 0 集"（旧行为取 TOTAL_EP + 完成时的 CURRENT_EP 相减恒为 0）
            total = row.TOTAL or row.TOTAL_EP
            over_edition = bool(row.OVER_EDITION) if hasattr(row, "OVER_EDITION") else False
            owner_user_id = getattr(row, "USER_ID", None)
            image = str(getattr(row, "IMAGE", "") or "")
            if image and not str(getattr(media, "poster_path", "") or ""):
                media.poster_path = image
            media.user_id = owner_user_id
            current_profile = str(getattr(media, "content_profile", "") or "")
            if not current_profile or current_profile == "default":
                media.content_profile = str(getattr(row, "CONTENT_PROFILE", None) or "default")
            self._history_repo.upsert(
                rssid=rssid,
                rtype=rtype,
                name=row.NAME,
                year=row.YEAR,
                season=row.SEASON,
                tmdbid=row.TMDBID if _row_ref(row).startswith("tmdb:") else "",
                image=media.get_poster_image() or image,
                desc=media.overview,
                total=total,
                start=row.CURRENT_EP,
                user_id=owner_user_id,
                **_history_scope(row),
            )
            _record_subscription_completed(row, rssid, "tv")
            delete_subscribe_fn(mtype=MediaType.TV, rssid=rssid)
            self._finish_sibling_tvs(row, media, delete_subscribe_fn)

        # 仅洗版订阅完成后清理下载历史（允许后续升级重下）；
        # 普通订阅保留下载历史，避免重新订阅时重复下载已完成的剧集
        if self._download_repo and (media.type == MediaType.MOVIE or over_edition):
            season_prefix = media.get_season_string() if media.type != MediaType.MOVIE else None
            identity_id = str(getattr(row, "IDENTITY_ID", "") or "")
            anchor_provider = str(getattr(row, "ANCHOR_PROVIDER", "") or "")
            anchor_external = str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "")
            if identity_id or (anchor_provider and anchor_external):
                self._download_repo.delete_by_identity(
                    identity_id=identity_id or None,
                    anchor_provider=anchor_provider or None,
                    anchor_external_id=anchor_external or None,
                    season_prefix=season_prefix,
                )
            elif media.tmdb_id:
                self._download_repo.delete_by_tmdb(media.tmdb_id, season_prefix)

        self._event_bus.publish(
            Event(
                event_type=SUBSCRIBE_FINISHED, payload=SubscribeFinishedPayload(media_info=media.to_dict(), rssid=rssid)
            )
        )
        log.info(
            f"[Subscribe]{media.type.value} {media.get_title_string()} "
            f"{media.get_season_string()} 订阅完成，删除订阅..."
        )
        self._message.send_rss_finished_message(media_info=media, owner_user_id=owner_user_id)

    def finalize_tv_by_rssid(self, rssid: int | None, mtype: MediaType | None, delete_subscribe_fn) -> None:
        """转移确认后按订阅行定稿：写历史、删订阅、联动兄弟、发通知。

        与 finish_rss_subscribe 不同，无需完整 media 对象：转移事件仅携带 tmdb/季/集，
        所需字段从订阅行恢复，避免依赖转移链路构造媒体。
        """
        if not rssid:
            return
        lock = get_lock_manager().create_lock(f"subscribe:finalize:tv:{rssid}", ttl_seconds=60)
        locked = lock.acquire()
        if not locked and lock.last_error is None:
            log.warn(f"[Subscribe]电视剧订阅 {rssid} 正在定稿，跳过重复事件")
            return
        if not locked:
            log.warn(f"[Subscribe]订阅 {rssid} 定稿锁后端不可用，继续无锁执行：{lock.last_error}")
        try:
            rss = self._tv_repo.get_all(rssid=rssid)
            if not rss:
                return
            row = rss[0]
            resolved_type = mtype or MediaType.TV
            row_profile = str(getattr(row, "CONTENT_PROFILE", "") or "").strip()
            if row_profile == "anime" and resolved_type != MediaType.ANIME:
                resolved_type = MediaType.ANIME
            elif resolved_type == MediaType.ANIME and row_profile in ("", "default"):
                row_profile = "anime"
            media = MediaInfo(
                type=resolved_type,
                tmdb_id=str(row.TMDBID or "") if _row_ref(row).startswith("tmdb:") else "",
            )
            media.title = row.NAME
            media.year = row.YEAR
            owner_user_id = getattr(row, "USER_ID", None)
            media.poster_path = str(getattr(row, "IMAGE", "") or "")
            media.user_id = owner_user_id
            season_str = str(row.SEASON).strip() if row.SEASON is not None else ""
            if season_str.isdigit():
                media.begin_season = int(season_str)
            media.over_edition = bool(row.OVER_EDITION)
            media.content_profile = row_profile or "default"
            media.anchor_provider = getattr(row, "ANCHOR_PROVIDER", None)
            media.anchor_external_id = getattr(row, "ANCHOR_EXTERNAL_ID", None)
            media.keyword = getattr(row, "KEYWORD", None)
            media.provider = getattr(row, "PROVIDER", None)
            media.metadata_ref = getattr(row, "METADATA_REF", None)
            media.total_episodes = int(row.TOTAL or 0)
            total = row.TOTAL or row.TOTAL_EP
            scope = _history_scope(row)
            if resolved_type == MediaType.ANIME and str(scope.get("content_profile") or "").strip() in ("", "default"):
                scope["content_profile"] = "anime"
            self._history_repo.upsert(
                rssid=rssid,
                rtype=MediaTypeMapper.to_tmdb(resolved_type),
                name=row.NAME,
                year=row.YEAR,
                season=row.SEASON,
                tmdbid=row.TMDBID if _row_ref(row).startswith("tmdb:") else "",
                image=row.IMAGE,
                desc=row.DESC,
                total=total,
                start=row.CURRENT_EP,
                user_id=owner_user_id,
                **scope,
            )
            _record_subscription_completed(row, rssid, resolved_type.value)
            delete_subscribe_fn(mtype=MediaType.TV, rssid=rssid)
            self._finish_sibling_tvs(row, media, delete_subscribe_fn)
            if self._download_repo and media.over_edition:
                identity_id = str(getattr(row, "IDENTITY_ID", "") or "")
                anchor_provider = str(getattr(row, "ANCHOR_PROVIDER", "") or "")
                anchor_external = str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "")
                if identity_id or (anchor_provider and anchor_external):
                    self._download_repo.delete_by_identity(
                        identity_id=identity_id or None,
                        anchor_provider=anchor_provider or None,
                        anchor_external_id=anchor_external or None,
                        season_prefix=media.get_season_string(),
                    )
                elif media.tmdb_id:
                    self._download_repo.delete_by_tmdb(media.tmdb_id, media.get_season_string())
            self._event_bus.publish(
                Event(
                    event_type=SUBSCRIBE_FINISHED,
                    payload=SubscribeFinishedPayload(media_info=media.to_dict(), rssid=rssid),
                )
            )
            log.info(f"[Subscribe]{resolved_type.value} {media.get_title_string()} 订阅完成（转移确认），删除订阅...")
            self._message.send_rss_finished_message(media_info=media, owner_user_id=owner_user_id)
        finally:
            if locked:
                lock.release()

    def finalize_movie_by_rssid(self, rssid: int | None, delete_subscribe_fn) -> None:
        """转移确认后按订阅行定稿电影订阅：写历史、删订阅、发通知。"""
        if not rssid:
            return
        lock = get_lock_manager().create_lock(f"subscribe:finalize:movie:{rssid}", ttl_seconds=60)
        locked = lock.acquire()
        if not locked and lock.last_error is None:
            log.warn(f"[Subscribe]电影订阅 {rssid} 正在定稿，跳过重复事件")
            return
        if not locked:
            log.warn(f"[Subscribe]订阅 {rssid} 定稿锁后端不可用，继续无锁执行：{lock.last_error}")
        try:
            rss = self._movie_repo.get_all(rssid=rssid)
            if not rss:
                return
            row = rss[0]
            owner_user_id = getattr(row, "USER_ID", None)
            over_edition = bool(getattr(row, "OVER_EDITION", False))
            # 删除订阅前固化通知/历史所需字段（尤其是 IMAGE 海报）。
            image = str(getattr(row, "IMAGE", "") or "")
            media = MediaInfo(
                type=MediaType.MOVIE,
                tmdb_id=str(row.TMDBID or "") if _row_ref(row).startswith("tmdb:") else "",
            )
            media.title = row.NAME
            media.year = row.YEAR
            media.poster_path = image
            media.user_id = owner_user_id
            media.over_edition = over_edition
            media.content_profile = str(getattr(row, "CONTENT_PROFILE", None) or "default")
            media.anchor_provider = getattr(row, "ANCHOR_PROVIDER", None)
            media.anchor_external_id = getattr(row, "ANCHOR_EXTERNAL_ID", None)
            media.keyword = getattr(row, "KEYWORD", None)
            media.provider = getattr(row, "PROVIDER", None)
            media.metadata_ref = getattr(row, "METADATA_REF", None)
            self._history_repo.upsert(
                rssid=rssid,
                rtype=MediaTypeMapper.to_tmdb(MediaType.MOVIE),
                name=row.NAME,
                year=row.YEAR,
                tmdbid=row.TMDBID if _row_ref(row).startswith("tmdb:") else "",
                image=image,
                desc=row.DESC,
                user_id=owner_user_id,
                **_history_scope(row),
            )
            _record_subscription_completed(row, rssid, "movie")
            delete_subscribe_fn(mtype=MediaType.MOVIE, rssid=rssid)
            # 仅洗版电影完成后清理下载历史（允许后续升级重下），优先按多元身份清理。
            if self._download_repo and over_edition:
                identity_id = str(getattr(row, "IDENTITY_ID", "") or "")
                anchor_provider = str(getattr(row, "ANCHOR_PROVIDER", "") or "")
                anchor_external = str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "")
                if identity_id or (anchor_provider and anchor_external):
                    self._download_repo.delete_by_identity(
                        identity_id=identity_id or None,
                        anchor_provider=anchor_provider or None,
                        anchor_external_id=anchor_external or None,
                    )
                elif row.TMDBID:
                    self._download_repo.delete_by_tmdb(row.TMDBID, None)
            self._event_bus.publish(
                Event(
                    event_type=SUBSCRIBE_FINISHED,
                    payload=SubscribeFinishedPayload(media_info=media.to_dict(), rssid=rssid),
                )
            )
            log.info(f"[Subscribe]movie {media.get_title_string()} 订阅完成（转移确认），删除订阅...")
            self._message.send_rss_finished_message(media_info=media, owner_user_id=owner_user_id)
        finally:
            if locked:
                lock.release()
