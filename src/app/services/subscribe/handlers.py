"""订阅领域事件处理器.

由 app.di.factories 在对象图构建完成后显式注册，避免事件处理器直接访问 registry。
"""

import log
from app.db.repositories.subscribe_repo_adapter import SubscribeTvRepositoryAdapter
from app.domain.entities.rss import SubscribeState
from app.events import Event, on_event
from app.events.constants import (
    MEDIA_EPISODE_TRANSFERRED,
    RSS_AUTO_SUBSCRIBE_REQUESTED,
    SUBSCRIBE_ADD,
    SUBSCRIBE_FINISHED,
)
from app.events.payloads import (
    MediaEpisodeTransferredPayload,
    RssAutoSubscribeRequestedPayload,
    SubscribeAddPayload,
    SubscribeFinishedPayload,
)
from app.services.subscribe.management.service import SubscribeService


@on_event(SUBSCRIBE_FINISHED)
def handle_subscribe_finished(event: Event) -> None:
    """订阅完成事件处理器"""
    payload = SubscribeFinishedPayload(**event.payload)
    log.info(f"[Event]订阅完成: rssid={payload.rssid}")


@on_event(SUBSCRIBE_ADD)
def handle_subscribe_add(event: Event) -> None:
    """订阅添加事件处理器"""
    payload = SubscribeAddPayload(**event.payload)
    log.info(f"[Event]订阅添加: rssid={payload.rssid}")


def build_rss_auto_subscribe_handler(subscribe_service: SubscribeService):
    """构造 RSS 自动订阅事件处理器并注册到事件系统。"""

    @on_event(RSS_AUTO_SUBSCRIBE_REQUESTED)
    def handle_rss_auto_subscribe(event: Event) -> None:
        """RSS自动化订阅请求处理器"""
        payload = RssAutoSubscribeRequestedPayload(**event.payload)
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


@on_event(MEDIA_EPISODE_TRANSFERRED)
def handle_media_episode_transferred(event: Event) -> None:
    """单集转移完成事件处理器 — 更新订阅进度"""
    payload = MediaEpisodeTransferredPayload(**event.payload)
    try:
        tv_repo = SubscribeTvRepositoryAdapter()
        raw_id = tv_repo.get_id(
            title=payload.title,
            season=payload.season,
            tmdbid=payload.tmdb_id,
        )
        rssid = int(raw_id) if raw_id is not None else None
        if not rssid:
            log.info(f"[Event]未找到订阅: tmdb_id={payload.tmdb_id} season={payload.season}")
            return

        total = payload.total_episodes
        if total > 0:
            all_episodes = set(range(1, total + 1))
            downloaded = set(payload.episodes)
            lack_episodes = sorted(list(all_episodes - downloaded))
        else:
            lack_episodes = []

        if lack_episodes:
            log.info(f"[Subscribe]更新电视剧 {payload.title} S{payload.season} 缺失集数为 {len(lack_episodes)}")
            tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state=SubscribeState.RUNNING.value)
            tv_repo.update_lack(title=None, year=None, season=None, rssid=rssid, lack_episodes=lack_episodes)
        else:
            log.info(f"[Subscribe]电视剧 {payload.title} S{payload.season} 全部集数已下载完成")
            tv_repo.update_state(title=None, year=None, season=None, rssid=rssid, state=SubscribeState.COMPLETED.value)
    except Exception as e:
        log.error(f"[Event]更新订阅进度失败：{e!s}")
