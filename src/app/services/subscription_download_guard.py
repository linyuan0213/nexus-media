"""订阅下载去重守卫.

只作用于订阅搜索：电影按整部、电视剧/动漫按分集，已有在途下载的分集不再重复下载。
洗版（over_edition）由订阅显式放行。
"""

from __future__ import annotations

from typing import Any

import log
from app.domain.interfaces.download_repo import IDownloadHistoryRepository


class SubscriptionDownloadGuard:
    def __init__(self, download_repo: IDownloadHistoryRepository):
        self._download_repo = download_repo

    def filter_candidates(self, media_list: list[Any], *, over_edition: bool = False) -> list[Any]:
        if over_edition:
            return list(media_list)
        result: list[Any] = []
        for media_item in media_list:
            season_episode = str(media_item.get_season_episode_string() or "").strip()
            if self._download_repo.has_active_download_for_media(
                identity_id=getattr(media_item, "identity_id", None),
                anchor_provider=getattr(media_item, "anchor_provider", None),
                anchor_external_id=getattr(media_item, "anchor_external_id", None),
                season_episode=season_episode,
            ):
                log.info(
                    f"[SubscriptionGuard]{getattr(media_item, 'title', '')} "
                    f"{season_episode or '整部'} 已有在途下载，跳过重复下载"
                )
                continue
            result.append(media_item)
        return result
