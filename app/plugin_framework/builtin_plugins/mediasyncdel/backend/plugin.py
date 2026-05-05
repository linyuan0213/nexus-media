# -*- coding: utf-8 -*-
"""
MediaSyncDel Plugin v2
Emby删除媒体后同步删除历史记录或源文件
"""
import os
import time

from app.media import Media
from app.plugin_framework.context import PluginContext
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.utils.types import MediaType


class MediaSyncDelPlugin:
    """Emby同步删除插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._filetransfer = FileTransfer()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("Emby同步删除插件已启用")

    def on_disable(self):
        self.ctx.info("Emby同步删除插件已禁用")

    def on_hook(self, event, data):
        if event == "webhook.emby":
            self._sync_del(data or {})

    def _sync_del(self, event_data):
        config = self._get_config()
        if not config.get("enable"):
            return

        event_type = event_data.get("Event")
        if not event_type or str(event_type) != 'library.deleted':
            return

        item_path = event_data.get('Item', {}).get('Path')
        if not item_path:
            return

        item = event_data.get('Item')
        media_type = item.get("Type")
        media_name = item.get("Name")
        series_name = item.get("SeriesName")
        media_path = item.get("Path")
        tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
        series_tmdb_id = item.get("SeriesProviderIds", {}).get("Tmdb")
        season_num = item.get("ParentIndexNumber")
        episode_num = item.get("IndexNumber")

        if not media_type:
            self.ctx.error(f"{media_name} 同步删除失败，未获取到媒体类型")
            return

        if media_type in ["Season", "Episode"]:
            if series_tmdb_id:
                tmdb_id = series_tmdb_id
            if series_name:
                media_name = series_name

        if not tmdb_id or not str(tmdb_id).isdigit():
            self.ctx.error(f"{media_name} 同步删除失败，未获取到TMDB ID")
            return

        if season_num is not None and str(season_num).isdigit():
            season_num = str(season_num).rjust(2, '0')
        if episode_num is not None and str(episode_num).isdigit():
            episode_num = str(episode_num).rjust(2, '0')

        exclude_path = config.get("exclude_path")
        if exclude_path and media_path and any(
                os.path.abspath(media_path).startswith(os.path.abspath(p)) for p in exclude_path.split(",")):
            self.ctx.info(f"媒体路径 {media_path} 已被排除，暂不处理")
            return

        if media_type == "Movie":
            msg = f'电影 {media_name} {tmdb_id}'
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id)
        elif media_type == "Series":
            msg = f'剧集 {media_name} {tmdb_id}'
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id)
        elif media_type == "Season":
            if not season_num or not str(season_num).isdigit():
                self.ctx.error(f"{media_name} 季同步删除失败，未获取到具体季")
                return
            msg = f'剧集 {media_name} S{season_num} {tmdb_id}'
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id, season=f'S{season_num}')
        elif media_type == "Episode":
            if not season_num or not str(season_num).isdigit() or not episode_num or not str(episode_num).isdigit():
                self.ctx.error(f"{media_name} 集同步删除失败，未获取到具体集")
                return
            msg = f'剧集 {media_name} S{season_num}E{episode_num} {tmdb_id}'
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id, season_episode=f'S{season_num} E{episode_num}')
        else:
            return

        if not transfer_history:
            return

        if media_type == "Episode" or media_type == "Movie":
            logids = [history.ID for history in transfer_history if history.DEST_FILENAME == os.path.basename(media_path)]
        else:
            logids = [history.ID for history in transfer_history]

        if len(logids) == 0:
            self.ctx.warn(f"{media_type} {media_name} 未获取到可删除数据")
            return

        self.ctx.info(f"获取到删除媒体数量 {len(logids)}")
        FileTransfer().delete_history(
            logids=logids,
            flag="del_source" if config.get("del_source") else ""
        )

        if config.get("send_notify"):
            if media_type == "Episode":
                image_url = Media().get_episode_images(tv_id=tmdb_id, season_id=season_num, episode_id=episode_num, orginal=True)
            else:
                image_url = Media().get_tmdb_backdrop(
                    mtype=MediaType.MOVIE if media_type == "Movie" else MediaType.TV,
                    tmdbid=tmdb_id
                )
            self.ctx.notify(
                title="【Emby同步删除任务完成】",
                image=image_url or 'https://emby.media/notificationicon.png',
                text=f"{msg}\n数量 {len(logids)}\n时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
            )

        self.ctx.info(f"同步删除 {msg} 完成！")
