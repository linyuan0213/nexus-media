"""
MediaSyncDel Plugin v2
Emby删除媒体后同步删除历史记录或源文件
"""

import os
import time

from app.media import MediaService
from app.plugin_framework.context import PluginContext
from app.domain.mediatypes import MediaType
from app.di import container


class MediaSyncDelPlugin:
    """Emby同步删除插件"""

    # 熔断器状态（类级变量，跨实例共享）
    _delete_events: list[tuple[float, str]] = []
    _circuit_breaker_tripped = False
    _circuit_breaker_reset_time = 0.0

    # 默认熔断参数
    DEFAULT_WINDOW = 300
    DEFAULT_TOTAL_THRESHOLD = 5
    DEFAULT_SAME_MEDIA_THRESHOLD = 3
    DEFAULT_COOLDOWN = 1800

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._filetransfer = container.filetransfer_service()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("Emby同步删除插件已启用")

    def on_disable(self):
        self.ctx.info("Emby同步删除插件已禁用")

    def on_hook(self, event, data):
        if event == "webhook.emby":
            self._sync_del(data or {})

    def _check_circuit_breaker(self, tmdb_id: str, config: dict) -> bool:
        """检查是否触发批量删除熔断，防止挂载丢失等异常导致误删"""
        now = time.time()
        window = config.get("cb_window", self.DEFAULT_WINDOW)
        total_threshold = config.get("cb_total_threshold", self.DEFAULT_TOTAL_THRESHOLD)
        same_threshold = config.get("cb_same_threshold", self.DEFAULT_SAME_MEDIA_THRESHOLD)
        cooldown = config.get("cb_cooldown", self.DEFAULT_COOLDOWN)

        # 清理过期事件
        self._delete_events = [(ts, tid) for ts, tid in self._delete_events if now - ts < window]

        # 检查是否处于熔断冷却期
        if self._circuit_breaker_tripped:
            if now < self._circuit_breaker_reset_time:
                self.ctx.warn(
                    f"[熔断保护]批量删除熔断中，跳过 {tmdb_id} 的删除事件，"
                    f"将在 {int(self._circuit_breaker_reset_time - now)} 秒后自动恢复"
                )
                return True
            self._circuit_breaker_tripped = False
            self.ctx.info("[熔断保护]批量删除熔断已自动恢复")

        # 记录当前事件
        self._delete_events.append((now, str(tmdb_id)))

        # 检查总事件数
        total_count = len(self._delete_events)
        if total_count >= total_threshold:
            self._circuit_breaker_tripped = True
            self._circuit_breaker_reset_time = now + cooldown
            self.ctx.error(
                f"[熔断保护]触发批量删除熔断！{window} 秒内收到 {total_count} 个删除事件，"
                f"远超阈值 {total_threshold}。可能是挂载丢失或Emby异常导致误报。"
                f"暂停处理删除事件 {cooldown} 秒，请检查媒体库状态。"
            )
            if config.get("send_notify"):
                self.ctx.notify(
                    title="[Emby同步删除熔断告警]",
                    text=f"{window} 秒内收到 {total_count} 个删除事件，已触发熔断保护。\n"
                    f"可能是挂载丢失或Emby异常导致误报，请检查媒体库状态。\n"
                    f"暂停处理 {cooldown} 秒后自动恢复。",
                )
            return True

        # 检查同一媒体事件数
        same_media_count = sum(1 for _, tid in self._delete_events if tid == str(tmdb_id))
        if same_media_count >= same_threshold:
            self._circuit_breaker_tripped = True
            self._circuit_breaker_reset_time = now + cooldown
            self.ctx.error(
                f"[熔断保护]触发批量删除熔断！媒体 {tmdb_id} 在 {window} 秒内"
                f"收到 {same_media_count} 个删除事件，远超阈值 {same_threshold}。"
                f"暂停处理删除事件 {cooldown} 秒。"
            )
            if config.get("send_notify"):
                self.ctx.notify(
                    title="[Emby同步删除熔断告警]",
                    text=f"媒体 {tmdb_id} 在 {window} 秒内收到 {same_media_count} 个删除事件，"
                    f"已触发熔断保护。\n"
                    f"暂停处理 {cooldown} 秒后自动恢复。",
                )
            return True

        return False

    def _sync_del(self, event_data):
        config = self._get_config()
        if not config.get("enable"):
            return

        event_type = event_data.get("Event")
        if not event_type or str(event_type) != "library.deleted":
            return

        item_path = event_data.get("Item", {}).get("Path")
        if not item_path:
            return

        item = event_data.get("Item")
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
            season_num = str(season_num).rjust(2, "0")
        if episode_num is not None and str(episode_num).isdigit():
            episode_num = str(episode_num).rjust(2, "0")

        # 批量删除熔断检查
        if self._check_circuit_breaker(str(tmdb_id), config):
            return

        exclude_path = config.get("exclude_path")
        if (
            exclude_path
            and media_path
            and any(os.path.abspath(media_path).startswith(os.path.abspath(p)) for p in exclude_path.split(","))
        ):
            self.ctx.info(f"媒体路径 {media_path} 已被排除，暂不处理")
            return

        if media_type == "Movie":
            msg = f"电影 {media_name} {tmdb_id}"
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id)
        elif media_type == "Series":
            msg = f"剧集 {media_name} {tmdb_id}"
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id)
        elif media_type == "Season":
            if not season_num or not str(season_num).isdigit():
                self.ctx.error(f"{media_name} 季同步删除失败，未获取到具体季")
                return
            msg = f"剧集 {media_name} S{season_num} {tmdb_id}"
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(tmdbid=tmdb_id, season=f"S{season_num}")
        elif media_type == "Episode":
            if not season_num or not str(season_num).isdigit() or not episode_num or not str(episode_num).isdigit():
                self.ctx.error(f"{media_name} 集同步删除失败，未获取到具体集")
                return
            msg = f"剧集 {media_name} S{season_num}E{episode_num} {tmdb_id}"
            self.ctx.info(f"正在同步删除{msg}")
            transfer_history = self._filetransfer.get_transfer_info_by(
                tmdbid=tmdb_id, season_episode=f"S{season_num} E{episode_num}"
            )
        else:
            return

        if not transfer_history:
            return

        if media_type == "Episode" or media_type == "Movie":
            logids = [
                history.ID for history in transfer_history if os.path.basename(media_path) == history.DEST_FILENAME
            ]
        else:
            logids = [history.ID for history in transfer_history]

        if len(logids) == 0:
            self.ctx.warn(f"{media_type} {media_name} 未获取到可删除数据")
            return

        # 删除前文件存在性校验：如果文件仍然实际存在，说明是Emby误报，跳过删除
        if config.get("check_file_exists", True):
            skip_logids = []
            for history in transfer_history:
                if history.ID not in logids:
                    continue
                dest_full = os.path.join(str(history.DEST or ""), str(history.DEST_FILENAME or ""))
                if dest_full and os.path.exists(dest_full):
                    self.ctx.warn(
                        f"[存在性保护]文件仍存在，跳过删除：{dest_full}\n"
                        f"可能是Emby误报删除事件（如挂载短暂失效后恢复），请检查媒体库状态。"
                    )
                    skip_logids.append(history.ID)
            if skip_logids:
                logids = [lid for lid in logids if lid not in skip_logids]
                self.ctx.info(f"[存在性保护]因文件仍存在，跳过 {len(skip_logids)} 条记录的删除")
            if not logids:
                self.ctx.info("[存在性保护]所有文件仍存在，取消本次删除操作")
                if config.get("send_notify"):
                    self.ctx.notify(
                        title="[Emby同步删除存在性保护]",
                        text=f"{msg}\nEmby上报删除但文件实际仍存在，已跳过删除。\n"
                        f"可能是挂载短暂失效导致Emby误报，请检查媒体库状态。",
                    )
                return

        self.ctx.info(f"获取到删除媒体数量 {len(logids)}")
        container.filetransfer_service().delete_history(
            logids=logids, flag="del_source" if config.get("del_source") else ""
        )

        if config.get("send_notify"):
            if media_type == "Episode":
                image_url = MediaService().get_episode_images(
                    tv_id=tmdb_id, season_id=season_num, episode_id=episode_num, orginal=True
                )
            else:
                image_url = MediaService().get_tmdb_backdrop(
                    mtype=MediaType.MOVIE if media_type == "Movie" else MediaType.TV, tmdbid=tmdb_id
                )
            self.ctx.notify(
                title="[Emby同步删除任务完成]",
                image=image_url or "https://emby.media/notificationicon.png",
                text=f"{msg}\n数量 {len(logids)}\n时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}",
            )

        self.ctx.info(f"同步删除 {msg} 完成！")
