"""订阅领域事件处理器.

由 app.di.factories 在对象图构建完成后显式注册，避免事件处理器直接访问 registry。
"""

from typing import Any

import log
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.db.repositories.subscribe_repo_adapter import (
    SubscribeMovieRepositoryAdapter,
    SubscribeTvEpisodeRepositoryAdapter,
    SubscribeTvRepositoryAdapter,
)
from app.domain.entities.rss import SubscribeState
from app.domain.mediatypes import MediaType
from app.events import Event, on_event
from app.events.constants import (
    MEDIA_EPISODE_TRANSFERRED,
    MEDIA_TRANSFER_FINISHED,
    RSS_AUTO_SUBSCRIBE_REQUESTED,
    SUBSCRIBE_ADD,
    SUBSCRIBE_FINISHED,
    TRANSFER_FAIL,
)
from app.events.payloads import (
    MediaEpisodeTransferredPayload,
    MediaTransferFinishedPayload,
    RssAutoSubscribeRequestedPayload,
    SubscribeAddPayload,
    SubscribeFinishedPayload,
    TransferFailPayload,
)
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.infrastructure.thread import ThreadExecutor
from app.media import MediaInfo
from app.media.parser import RegexParser
from app.services.subscribe.management.service import SubscribeService
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy


@on_event(SUBSCRIBE_FINISHED)
def handle_subscribe_finished(event: Event) -> None:
    """订阅完成事件处理器"""
    payload = event.payload
    if not isinstance(payload, SubscribeFinishedPayload):
        payload = SubscribeFinishedPayload(**payload)
    log.info(f"[Event]订阅完成: rssid={payload.rssid}")


@on_event(SUBSCRIBE_ADD)
def handle_subscribe_add(event: Event) -> None:
    """订阅添加事件处理器"""
    payload = event.payload
    if not isinstance(payload, SubscribeAddPayload):
        payload = SubscribeAddPayload(**payload)
    log.info(f"[Event]订阅添加: rssid={payload.rssid}")


def build_rss_auto_subscribe_handler(subscribe_service: SubscribeService):
    """构造 RSS 自动订阅事件处理器并注册到事件系统。"""

    @on_event(RSS_AUTO_SUBSCRIBE_REQUESTED)
    def handle_rss_auto_subscribe(event: Event) -> None:
        """RSS自动化订阅请求处理器"""
        payload = event.payload
        if not isinstance(payload, RssAutoSubscribeRequestedPayload):
            payload = RssAutoSubscribeRequestedPayload(**payload)
        try:
            code, msg, _ = subscribe_service.add_rss_subscribe(
                mtype=payload.mtype,
                name=payload.name,
                year=payload.year,
                season=payload.season,
                rss_sites=payload.rss_sites,
                search_sites=payload.search_sites,
                over_edition=payload.over_edition,
                filter_restype=payload.filter_restype,
                filter_pix=payload.filter_pix,
                filter_team=payload.filter_team,
                filter_rule=payload.filter_rule,
                save_path=payload.save_path,
                download_setting=payload.download_setting,
            )
            if code != 0:
                log.warn(f"[Event]自定义RSS订阅请求处理失败：{msg}")
            else:
                log.info(f"[Event]自定义RSS订阅请求已处理：{payload.name}")
        except Exception as e:
            log.error(f"[Event]处理自定义RSS订阅请求失败：{e!s}")

    return handle_rss_auto_subscribe


def handle_media_episode_transferred(event: Event, finalize_fn=None) -> None:
    """单集转移完成事件处理器 — 更新订阅进度；缺失清零时定稿（finalize_fn）。"""
    payload = event.payload
    if not isinstance(payload, MediaEpisodeTransferredPayload):
        payload = MediaEpisodeTransferredPayload(**payload)
    try:
        tv_repo = SubscribeTvRepositoryAdapter()
        ep_repo = SubscribeTvEpisodeRepositoryAdapter()
        rssid = None
        anchor_provider = str(payload.anchor_provider or "")
        anchor_external = str(payload.anchor_external_id or "")
        if anchor_provider and anchor_external:
            by_anchor = getattr(tv_repo, "get_id_by_anchor", None)
            if by_anchor:
                raw_anchor_id = by_anchor(
                    anchor_provider,
                    anchor_external,
                    season=payload.season,
                    content_profile=payload.content_profile,
                    user_id=payload.user_id,
                )
                rssid = int(raw_anchor_id) if raw_anchor_id is not None else None
        if not rssid:
            lookup_kwargs: dict[str, Any] = {
                "title": payload.title,
                "season": payload.season,
                "tmdbid": payload.tmdb_id,
            }
            if payload.user_id is not None:
                lookup_kwargs["user_id"] = payload.user_id
            raw_id = tv_repo.get_id(**lookup_kwargs)
            rssid = int(raw_id) if raw_id is not None else None
        if not rssid:
            log.info(
                f"[Event]未找到订阅: tmdb_id={payload.tmdb_id} "
                f"anchor={payload.anchor_provider}:{payload.anchor_external_id} season={payload.season}"
            )
            return

        downloaded = {int(e) for e in (payload.episodes or []) if str(e).isdigit()}
        if not downloaded:
            return

        # 在「当前缺失集」基础上减去本次转移的集。
        # 不能用「全集 - 本次转移集」重算，否则会把之前已入库的集误标回缺失，
        # 导致订阅进度倒退并重复下载。
        lock = get_lock_manager().create_lock(f"subscribe:progress:{rssid}", ttl_seconds=60)
        locked = lock.acquire()
        if not locked and lock.last_error is None:
            log.warn(f"[Subscribe]订阅 {rssid} 进度正在更新，跳过重复事件")
            return
        if not locked:
            log.warn(f"[Subscribe]订阅 {rssid} 锁后端不可用，继续无锁更新：{lock.last_error}")
        try:
            current_missing = ep_repo.get(rssid)
            if not current_missing:
                # 缺失列表未初始化或为空：以订阅的 current_ep（首个待下载集）推导初始范围。
                # 空列表不能直接视为“全部完成”，否则首集刚转移就会误写订阅历史。
                total = int(payload.total_episodes or 0)
                if total <= 0:
                    # 总集数未知时无法核定缺失，保持原状态，避免误判完成
                    log.info(f"[Subscribe]{payload.title} S{payload.season} 缺失未初始化且总集数未知，跳过更新")
                    return
                subs = tv_repo.get_all(rssid=rssid)
                start = int(subs[0].current_ep) if subs and subs[0].current_ep else 1
                current_missing = list(range(start, total + 1))

            lack_episodes = sorted(set(int(e) for e in current_missing) - downloaded)

            if lack_episodes:
                log.info(f"[Subscribe]更新电视剧 {payload.title} S{payload.season} 缺失集数为 {len(lack_episodes)}")
                subs = tv_repo.get_all(rssid=rssid)
                pending = bool(subs) and subs[0].state == SubscribeState.COMPLETED.value
                if not pending:
                    # 仅对仍在轮询的订阅保持 RUNNING；待转移(COMPLETED)订阅在分批转移期间保持完成态，
                    # 否则会被 RSS 重新匹配导致重复下载；缺失清空后再定稿。
                    tv_repo.update_state(
                        title=None, year=None, season=None, rssid=rssid, state=SubscribeState.RUNNING.value
                    )
                tv_repo.update_lack(title=None, year=None, season=None, rssid=rssid, lack_episodes=lack_episodes)
            else:
                log.info(f"[Subscribe]电视剧 {payload.title} S{payload.season} 转移确认全部集数完成")
                if finalize_fn:
                    # 转移落盘确认 → 定稿：写历史、删订阅、联动兄弟、发通知
                    finalize_fn(rssid, payload)
                else:
                    # 无定稿回调（如单测直调）：仅标记完成，不删订阅（避免空串写回）
                    tv_repo.update_state(
                        title=None, year=None, season=None, rssid=rssid, state=SubscribeState.COMPLETED.value
                    )
        finally:
            if locked:
                lock.release()
    except Exception as e:
        log.error(f"[Event]更新订阅进度失败：{e!s}")


def build_media_episode_transferred_handler(subscribe_service: SubscribeService):
    """构造转移定稿处理器：转移落盘确认后按订阅行定稿（写历史、删订阅、联动兄弟）。"""

    def _finalize(rssid, payload) -> None:
        mtype = None
        media_type = getattr(payload, "media_type", None)
        if media_type:
            try:
                mtype = MediaType(media_type)
            except ValueError:
                mtype = None
        subscribe_service.finalize_tv_by_rssid(rssid, mtype)

    @on_event(MEDIA_EPISODE_TRANSFERRED)
    def _handle(event: Event) -> None:
        handle_media_episode_transferred(event, finalize_fn=_finalize)

    return _handle


def build_movie_transfer_finalize_handler(subscribe_service: SubscribeService):
    """构造电影定稿处理器：电影入库确认后按订阅行定稿。

    以“媒体库已存在”为定稿依据，避免电影目录内附加文件(nfo/sample/字幕等)
    先落盘即触发过早定稿；未入库则等待后续转移或由待转移清理兜底。
    """

    @on_event(MEDIA_TRANSFER_FINISHED)
    def _handle(event: Event) -> None:
        payload = event.payload
        if not isinstance(payload, MediaTransferFinishedPayload):
            payload = MediaTransferFinishedPayload(**payload)
        info = payload.media_info or {}
        if info.get("type") != MediaType.MOVIE.value:
            return
        profile = str(info.get("content_profile") or "default")
        anchor_provider = str(info.get("anchor_provider") or "").strip()
        anchor_external = str(info.get("anchor_external_id") or "").strip()
        tmdb = str(info.get("tmdb_id") or info.get("id") or info.get("orgid") or "")
        if not tmdb and profile == "default" and not (anchor_provider and anchor_external):
            return
        media = MediaInfo(type=MediaType.MOVIE, tmdb_id=tmdb)
        media.title = info.get("title") or ""
        media.year = info.get("year") or ""
        media.overview = info.get("overview") or ""
        # TMDB 只用于普通电影入库判定；插件内容画像以订阅锚点/转移事件为准。
        if tmdb and profile == "default" and not subscribe_service.media_exists(media):
            return
        seen: set = set()
        for sub in SubscribeMovieRepositoryAdapter().get_all():
            sid = getattr(sub, "id", None)
            if not sid or sid in seen:
                continue
            row_tmdb = str(getattr(sub, "tmdb_id", "") or "")
            row_external = str(getattr(sub, "anchor_external_id", "") or "")
            matched = bool(tmdb) and row_tmdb == tmdb
            if not matched and anchor_external and row_external == anchor_external:
                # 转移事件的锚点可能来自 content_id，而订阅行来自具体 provider；
                # 同一内容编号/锚点即可定稿，不能要求两边 provider 完全一致。
                matched = True
            if not matched:
                continue
            seen.add(sid)
            subscribe_service.finalize_movie_by_rssid(sid)

    return _handle


def build_transfer_fail_reopen_handler(subscribe_service: SubscribeService):
    """构造转移失败回滚处理器：重开对应订阅、回补失败集缺失并复位下载历史，允许重新下载。"""

    @on_event(TRANSFER_FAIL)
    def _handle(event: Event) -> None:
        payload = event.payload
        if not isinstance(payload, TransferFailPayload):
            payload = TransferFailPayload(**payload)
        path = payload.path
        if not path:
            return
        try:
            history = DownloadHistoryRepositoryAdapter().get_by_path(path)
            if not history:
                return
            history_tmdb = str(getattr(history, "tmdb_id", "") or "")
            history_provider = str(getattr(history, "anchor_provider", "") or "")
            history_external = str(getattr(history, "anchor_external_id", "") or "")
            if not history_tmdb and not (history_provider and history_external):
                return
            parsed = RegexParser().parse(str(history.season_episode or ""))
            season = str(parsed.season) if parsed and parsed.season is not None else None
            # 本次失败的集号：回补到订阅缺失，避免下载时已被移除的集不再重试
            failed_eps: list[int] = []
            if parsed and parsed.episode is not None:
                end = parsed.end_episode or parsed.episode
                failed_eps = list(range(int(parsed.episode), int(end) + 1))
            reopened = 0
            # 仅回滚该次下载归属用户的订阅，避免波及同媒体其他用户（ADR-021 记账分离）
            owner = getattr(history, "user_id", None)
            tv_repo = SubscribeTvRepositoryAdapter()
            ep_repo = SubscribeTvEpisodeRepositoryAdapter()
            history_identity = str(getattr(history, "identity_id", "") or "")
            for sub in tv_repo.get_all():
                row_tmdb = str(getattr(sub, "tmdb_id", "") or "")
                row_external = str(getattr(sub, "anchor_external_id", "") or "")
                row_identity = str(getattr(sub, "identity_id", "") or "")
                matched = bool(history_tmdb) and row_tmdb == history_tmdb
                if not matched and history_external and row_external == history_external:
                    # 同一锚点即视为同一订阅，兼容转移链路的 content_id 锚点。
                    matched = True
                if not matched and history_identity and row_identity == history_identity:
                    matched = True
                if not matched:
                    continue
                if season is not None and str(sub.season) != season:
                    continue
                if owner is not None and getattr(sub, "user_id", None) != owner:
                    continue
                subscribe_service.update_rss_state(MediaType.TV, sub.id, SubscribeState.RUNNING.value)
                if failed_eps:
                    current = ep_repo.get(sub.id) or []
                    merged = sorted(set(int(e) for e in current) | set(failed_eps))
                    if merged:
                        tv_repo.update_lack(title=None, year=None, season=None, rssid=sub.id, lack_episodes=merged)
                reopened += 1
            # 电影订阅：重开以便重新匹配下载（无 TMDB 的插件画像按锚点匹配）
            for msub in SubscribeMovieRepositoryAdapter().get_all():
                row_tmdb = str(getattr(msub, "tmdb_id", "") or "")
                matched = bool(history_tmdb) and row_tmdb == history_tmdb
                if not matched and history_provider and history_external:
                    row_external = str(getattr(msub, "anchor_external_id", "") or "")
                    row_providers = {
                        str(getattr(msub, "provider", "") or ""),
                        str(getattr(msub, "anchor_provider", "") or ""),
                    }
                    matched = row_external == history_external and history_provider in row_providers
                if not matched:
                    continue
                if owner is not None and getattr(msub, "user_id", None) != owner:
                    continue
                subscribe_service.update_rss_state(MediaType.MOVIE, msub.id, SubscribeState.RUNNING.value)
                reopened += 1
            # 复位下载历史状态，解除“已完成”过滤，使订阅可重新匹配下载
            DownloadHistoryRepositoryAdapter().update_state(history.downloader, history.download_id, "downloading")
            log.info(f"[Event]转移失败回滚：tmdb_id={history.tmdb_id} 重开订阅 {reopened} 个，复位下载历史")
        except Exception as e:
            log.error(f"[Event]转移失败回滚失败：{e!s}")

    return _handle


def build_subscribe_add_search_handler(queue_strategy: QueueSearchStrategy, thread_executor: ThreadExecutor):
    """构造订阅添加/更新后自动触发队列搜索的事件处理器。"""

    @on_event(SUBSCRIBE_ADD)
    def _handle(event: Event) -> None:
        payload = event.payload
        if not isinstance(payload, SubscribeAddPayload):
            payload = SubscribeAddPayload(**payload)
        log.info(f"[Event]订阅添加/更新 rssid={payload.rssid}，触发即时队列搜索")

        def _search():
            try:
                queue_strategy.run()
            except Exception as e:
                log.error(f"[Event]触发队列搜索失败：{e}")

        thread_executor.submit(_search)

    return _handle
