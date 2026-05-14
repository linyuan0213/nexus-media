from app.core.system_config import SystemConfig
from app.helper import ThreadHelper
from app.infrastructure.cache_system import TokenCache
from app.mediaserver import MediaServer
from app.schemas.media import LibrarySpaceDTO
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.media_config_service import MediaConfigService
from app.utils import SystemUtils
from app.utils.types import SystemConfigKey


class MediaLibraryService:
    """
    媒体库业务服务
    """

    def __init__(self, media_server: MediaServer | None = None, filetransfer: FileTransfer | None = None):
        self._media_server = media_server or MediaServer()
        self._filetransfer = filetransfer or FileTransfer()

    def get_sync_state(self) -> str:
        """获取同步状态文本"""
        status = self._media_server.get_mediasync_status()
        if not status:
            return "未同步"
        return "电影：{}，电视剧：{}，同步时间：{}".format(
            status.get("movie_count"),
            status.get("tv_count"),
            status.get("time"),
        )

    def start_sync(self, librarys: list):
        """开始媒体库同步"""
        TokenCache.delete("index")
        SystemConfig().set(key=SystemConfigKey.SyncLibrary, value=librarys)
        ThreadHelper().start_thread(self._media_server.sync_mediaserver, ())

    def get_media_count(self) -> dict | None:
        """获取媒体库统计"""
        media_counts = self._media_server.get_medias_count()
        user_count = self._media_server.get_user_count()
        if media_counts:
            return {
                "Movie": "{:,}".format(media_counts.get("MovieCount")),
                "Series": "{:,}".format(media_counts.get("SeriesCount")),
                "Episodes": "{:,}".format(media_counts.get("EpisodeCount")) if media_counts.get("EpisodeCount") else "",
                "Music": "{:,}".format(media_counts.get("SongCount")),
                "User": user_count,
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
        media_cfg = MediaConfigService().get_config()
        movie_paths = media_cfg.get("movie_path") or []
        tv_paths = media_cfg.get("tv_path") or []
        anime_paths = media_cfg.get("anime_path") or []

        all_paths = movie_paths + tv_paths + anime_paths
        if not all_paths:
            return LibrarySpaceDTO()

        space_result = SystemUtils.calculate_space_usage(all_paths)
        if not isinstance(space_result, tuple):
            return LibrarySpaceDTO()
        total_space, free_space = space_result
        if not total_space:
            return LibrarySpaceDTO()

        used_space = total_space - free_space
        used_percent = "%0.1f" % ((used_space / total_space) * 100)

        def fmt_space(val):
            if val > 1024:
                return f"{round(val / 1024, 2):,} TB"
            return f"{round(val, 2):,} GB"

        return LibrarySpaceDTO(
            used_percent=used_percent,
            free_space=fmt_space(free_space),
            used_space=fmt_space(used_space),
            total_space=fmt_space(total_space),
        )
