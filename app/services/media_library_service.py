# -*- coding: utf-8 -*-
from typing import Optional

from app.core.system_config import SystemConfig
from app.helper import ThreadHelper
from app.mediaserver import MediaServer
from app.schemas.media import LibrarySpaceDTO
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.utils import SystemUtils, TokenCache
from app.utils.types import SystemConfigKey
from config import Config


class MediaLibraryService:
    """
    媒体库业务服务
    """

    def __init__(self,
                 media_server: Optional[MediaServer] = None,
                 filetransfer: Optional[FileTransfer] = None):
        self._media_server = media_server or MediaServer()
        self._filetransfer = filetransfer or FileTransfer()

    def get_sync_state(self) -> str:
        """获取同步状态文本"""
        status = self._media_server.get_mediasync_status()
        if not status:
            return "未同步"
        return "电影：%s，电视剧：%s，同步时间：%s" % (
            status.get("movie_count"), status.get("tv_count"), status.get("time"))

    def start_sync(self, librarys: list):
        """开始媒体库同步"""
        TokenCache.delete("index")
        SystemConfig().set(key=SystemConfigKey.SyncLibrary, value=librarys)
        ThreadHelper().start_thread(self._media_server.sync_mediaserver, ())

    def get_media_count(self) -> Optional[dict]:
        """获取媒体库统计"""
        media_counts = self._media_server.get_medias_count()
        user_count = self._media_server.get_user_count()
        if media_counts:
            return {
                "Movie": "{:,}".format(media_counts.get('MovieCount')),
                "Series": "{:,}".format(media_counts.get('SeriesCount')),
                "Episodes": "{:,}".format(media_counts.get('EpisodeCount')) if media_counts.get('EpisodeCount') else "",
                "Music": "{:,}".format(media_counts.get('SongCount')),
                "User": user_count
            }
        return None

    def get_play_history(self) -> list:
        """获取播放记录"""
        return self._media_server.get_activity_log(30)

    def init_config(self):
        """初始化媒体服务器配置（代理）"""
        self._media_server.init_config()

    def get_libraries(self):
        """获取媒体库列表（代理）"""
        return self._media_server.get_libraries()

    def get_resume(self, num=12):
        """获取继续观看（代理）"""
        return self._media_server.get_resume(num=num)

    def get_latest(self, num=20):
        """获取最新入库（代理）"""
        return self._media_server.get_latest(num=num)

    def get_space_info(self) -> LibrarySpaceDTO:
        """获取媒体库存储空间"""
        media = Config().get_config('media')
        movie_paths = media.get('movie_path') or []
        if not isinstance(movie_paths, list):
            movie_paths = [movie_paths]
        tv_paths = media.get('tv_path') or []
        if not isinstance(tv_paths, list):
            tv_paths = [tv_paths]
        anime_paths = media.get('anime_path') or []
        if not isinstance(anime_paths, list):
            anime_paths = [anime_paths]

        all_paths = movie_paths + tv_paths + anime_paths
        if not all_paths:
            return LibrarySpaceDTO()

        space_result = SystemUtils.calculate_space_usage(all_paths)
        if not isinstance(space_result, tuple):
            return LibrarySpaceDTO()
        TotalSpace, FreeSpace = space_result
        if not TotalSpace:
            return LibrarySpaceDTO()

        UsedSpace = TotalSpace - FreeSpace
        UsedPercent = "%0.1f" % ((UsedSpace / TotalSpace) * 100)

        def fmt_space(val):
            if val > 1024:
                return "{:,} TB".format(round(val / 1024, 2))
            return "{:,} GB".format(round(val, 2))

        return LibrarySpaceDTO(
            used_percent=UsedPercent,
            free_space=fmt_space(FreeSpace),
            used_space=fmt_space(UsedSpace),
            total_space=fmt_space(TotalSpace)
        )
