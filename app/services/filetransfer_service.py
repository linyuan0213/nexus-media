"""
FileTransferService - 文件转移业务 Facade
将 app/filetransfer.py 重构为依赖注入模式，
底层实现拆分到 TransferEngine 与 StorageBackend。
保留与原 FileTransfer 兼容的公共 API。
"""

import os
import random
import re
import shutil
from time import sleep

import log
from app.core.constants import DEFAULT_MOVIE_FORMAT, DEFAULT_TV_FORMAT, RMT_FAVTYPE, RMT_MEDIAEXT, RMT_MIN_FILESIZE
from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
from app.db.repositories.transfer_repo_adapter import (
    TransferBlacklistRepositoryAdapter,
    TransferHistoryRepositoryAdapter,
    TransferUnknownRepositoryAdapter,
)
from app.domain.interfaces.download_repo import IDownloadHistoryRepository
from app.domain.interfaces.transfer_repo import (
    ITransferBlacklistRepository,
    ITransferHistoryRepository,
    ITransferUnknownRepository,
)
from app.helper import ProgressHelper, ThreadHelper
from app.media import Category, MediaService, Scraper, meta_info
from app.message import Message
from app.plugin_framework.event_compat import EventManager
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.services.media_config_service import MediaConfigService
from app.services.transfer_engine import TransferEngine
from app.storage import StorageBackendFactory
from app.storage.backends.base import StorageConfig, StorageType
from app.storage.config_models import LocalStorageConfig
from app.storage.backends.local import LocalStorageBackend
from app.utils import ExceptionUtils, NumberUtils, PathUtils, StringUtils, SystemUtils
from app.utils.types import EventType, MediaType, MovieTypes, ProgressKey, SyncType
from config import Config


class FileTransferService:
    """
    文件转移业务 Facade
    保留与原 FileTransfer 兼容的公共 API，移除 SingletonMeta，改为依赖注入。
    """

    def __init__(
        self,
        media_service: MediaService | None = None,
        message: Message | None = None,
        category: Category | None = None,
        scraper: Scraper | None = None,
        threadhelper: ThreadHelper | None = None,
        transfer_repo: ITransferHistoryRepository | None = None,
        transfer_blacklist_repo: ITransferBlacklistRepository | None = None,
        transfer_unknown_repo: ITransferUnknownRepository | None = None,
        download_repo: IDownloadHistoryRepository | None = None,
        progress: ProgressHelper | None = None,
        eventmanager: EventManager | None = None,
        engine: TransferEngine | None = None,
    ):
        self.media = media_service or MediaService()
        self.message = message or Message()
        self.category = category or Category()
        self.scraper = scraper or Scraper()
        self.threadhelper = threadhelper or ThreadHelper()
        self.transfer_repo = transfer_repo or TransferHistoryRepositoryAdapter()
        self.transfer_blacklist_repo = transfer_blacklist_repo or TransferBlacklistRepositoryAdapter()
        self.transfer_unknown_repo = transfer_unknown_repo or TransferUnknownRepositoryAdapter()
        self.download_repo = download_repo or DownloadHistoryRepositoryAdapter()
        self.sync_repo = SyncPathRepositoryAdapter()
        self.progress = progress or ProgressHelper()
        self.eventmanager = eventmanager or EventManager()
        self._default_operation: str = "copy"
        self._movie_path: list = []
        self._tv_path: list = []
        self._anime_path: list = []
        self._movie_category_flag = None
        self._tv_category_flag = None
        self._anime_category_flag = None
        self._unknown_path: list = []
        self._min_filesize = RMT_MIN_FILESIZE
        self._filesize_cover = False
        self._movie_dir_rmt_format = ""
        self._movie_file_rmt_format = ""
        self._tv_dir_rmt_format = ""
        self._tv_season_rmt_format = ""
        self._tv_file_rmt_format = ""
        self._ignored_paths: re.Pattern[str] | None = None
        self._ignored_files: re.Pattern[str] | None = None
        self._engine = engine or TransferEngine()
        self.init_config()

    def init_config(self):
        self.media = MediaService()
        self.message = Message()
        self.category = Category()
        self.scraper = Scraper()
        self.threadhelper = ThreadHelper()
        self.transfer_repo = TransferHistoryRepositoryAdapter()
        self.transfer_blacklist_repo = TransferBlacklistRepositoryAdapter()
        self.transfer_unknown_repo = TransferUnknownRepositoryAdapter()
        self.download_repo = DownloadHistoryRepositoryAdapter()
        self.sync_repo = SyncPathRepositoryAdapter()
        self.progress = ProgressHelper()
        self.eventmanager = EventManager()

        media_cfg = MediaConfigService().get_config()
        media = Config().get_config("media")

        self._movie_path = media_cfg.get("movie_path") or []
        self._movie_backend = media_cfg.get("movie_backend") or []
        self._movie_category_flag = self.category.movie_category_flag
        self._tv_path = media_cfg.get("tv_path") or []
        self._tv_backend = media_cfg.get("tv_backend") or []
        self._tv_category_flag = self.category.tv_category_flag
        self._anime_path = media_cfg.get("anime_path") or []
        self._anime_backend = media_cfg.get("anime_backend") or []
        self._anime_category_flag = self.category.anime_category_flag
        if not self._anime_path:
            self._anime_path = self._tv_path
            self._anime_backend = self._tv_backend
            self._anime_category_flag = self._tv_category_flag
        self._unknown_path = media_cfg.get("unknown_path") or []
        self._unknown_backend = media_cfg.get("unknown_backend") or []

        if media:
            min_filesize = media.get("min_filesize")
            if isinstance(min_filesize, int):
                self._min_filesize = min_filesize * 1024 * 1024
            elif isinstance(min_filesize, str) and min_filesize.isdigit():
                self._min_filesize = int(min_filesize) * 1024 * 1024
            ignored_paths = media.get("ignored_paths")
            if ignored_paths:
                if ignored_paths.endswith(";"):
                    ignored_paths = ignored_paths[:-1]
                self._ignored_paths = re.compile(r"{}".format(re.sub(r";", r"|", ignored_paths)))
            ignored_files = media.get("ignored_files")
            if ignored_files:
                if ignored_files.endswith(";"):
                    ignored_files = ignored_files[:-1]
                self._ignored_files = re.compile(r"{}".format(re.sub(r";", r"|", ignored_files)))
            self._filesize_cover = media.get("filesize_cover")
            movie_name_format = media.get("movie_name_format") or DEFAULT_MOVIE_FORMAT
            movie_formats = movie_name_format.rsplit("/", 1)
            if movie_formats:
                self._movie_dir_rmt_format = movie_formats[0]
                if len(movie_formats) > 1:
                    self._movie_file_rmt_format = movie_formats[-1]
            tv_name_format = media.get("tv_name_format") or DEFAULT_TV_FORMAT
            tv_formats = tv_name_format.rsplit("/", 2)
            if tv_formats:
                self._tv_dir_rmt_format = tv_formats[0]
                if len(tv_formats) > 2:
                    self._tv_season_rmt_format = tv_formats[-2]
                    self._tv_file_rmt_format = tv_formats[-1]
        self._default_operation = Config().get_config("pt").get("rmt_mode", "copy") or "copy"

    def is_target_dir_path(self, path):
        """
        判断是否为目的路径下的路径
        :param path: 路径
        :return: True/False
        """
        if not path:
            return False
        for tv_path in self._tv_path:
            if PathUtils.is_path_in_path(tv_path, path):
                return True
        for movie_path in self._movie_path:
            if PathUtils.is_path_in_path(movie_path, path):
                return True
        for anime_path in self._anime_path:
            if PathUtils.is_path_in_path(anime_path, path):
                return True
        return any(PathUtils.is_path_in_path(unknown_path, path) for unknown_path in self._unknown_path)

    def _get_backend_for_path(self, path: str, path_list: list, backend_list: list) -> str:
        """根据路径查找对应的后端 ID"""
        if not backend_list:
            return "local"
        for idx, p in enumerate(path_list):
            if PathUtils.is_path_in_path(p, path) and idx < len(backend_list):
                return backend_list[idx] or "local"
        return "local"

    def _resolve_dst_backend(self, dist_path: str, mtype: MediaType):
        """根据目标路径和媒体类型解析目标存储后端"""
        backend_id = "local"
        if mtype == MediaType.MOVIE:
            backend_id = self._get_backend_for_path(dist_path, self._movie_path, self._movie_backend)
        elif mtype == MediaType.TV:
            backend_id = self._get_backend_for_path(dist_path, self._tv_path, self._tv_backend)
        else:
            backend_id = self._get_backend_for_path(dist_path, self._anime_path, self._anime_backend)
        if backend_id == "local":
            return None
        entity = StorageBackendRepositoryAdapter().get_by_id(int(backend_id))
        if not entity:
            return None
        info = StorageBackendFactory.get_config_info(entity.type)
        if info:
            stype, cls = info
        else:
            stype, cls = StorageType.LOCAL, LocalStorageConfig
        config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
        for k, v in entity.config.items():
            if hasattr(config, k):
                setattr(config, k, v)
        return StorageBackendFactory.create(config)

    def _is_media_exists(self, media_dest, media, dst_backend=None):
        """
        判断媒体文件是否已存在（支持本地和远程后端）
        :param media_dest: 媒体文件所在目录
        :param media: 已识别的媒体信息
        :param dst_backend: 目标存储后端，None 表示本地
        :return: 目录是否存在，目录路径，文件是否存在，文件路径
        """
        backend = dst_backend

        def _exists(path: str) -> bool:
            if backend is not None:
                return backend.exists(path)
            return os.path.exists(path)

        dir_exist_flag = False
        file_exist_flag = False
        ret_dir_path = None
        ret_file_path = None
        if media.type == MediaType.MOVIE:
            dir_name, file_name = self.get_moive_dest_path(media)
            file_path = os.path.join(media_dest, dir_name)
            if self._movie_category_flag:
                file_path = os.path.join(media_dest, media.category, dir_name)
                for m_type in [RMT_FAVTYPE, media.category]:
                    type_path = os.path.join(media_dest, m_type, dir_name)
                    if _exists(type_path):
                        file_path = type_path
                        break
            ret_dir_path = file_path
            if _exists(file_path):
                dir_exist_flag = True
            file_dest = os.path.join(file_path, file_name)
            ret_file_path = file_dest
            for ext in RMT_MEDIAEXT:
                ext_dest = f"{file_dest}{ext}"
                if _exists(ext_dest):
                    file_exist_flag = True
                    ret_file_path = ext_dest
                    break
        else:
            dir_name, season_name, file_name = self.get_tv_dest_path(media)
            if (media.type == MediaType.TV and self._tv_category_flag) or (
                media.type == MediaType.ANIME and self._anime_category_flag
            ):
                media_path = os.path.join(media_dest, media.category, dir_name)
            else:
                media_path = os.path.join(media_dest, dir_name)
            if media.get_season_list():
                season_dir = os.path.join(media_path, season_name)
                ret_dir_path = season_dir
                if _exists(season_dir):
                    dir_exist_flag = True
                episodes = media.get_episode_list()
                if episodes:
                    file_path = os.path.join(season_dir, file_name)
                    ret_file_path = file_path
                    for ext in RMT_MEDIAEXT:
                        ext_dest = f"{file_path}{ext}"
                        if _exists(ext_dest):
                            file_exist_flag = True
                            ret_file_path = ext_dest
                            break
        return dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path

    def get_dest_path_by_info(self, dest, meta_info):
        """
        拼装转移重命名后的新文件地址
        :param dest: 目的目录
        :param meta_info: 媒体信息
        """
        if not dest or not meta_info:
            return None
        if meta_info.type == MediaType.MOVIE:
            dir_name, _ = self.get_moive_dest_path(meta_info)
            if self._movie_category_flag:
                return os.path.join(dest, meta_info.category, dir_name)
            else:
                return os.path.join(dest, dir_name)
        else:
            dir_name, season_name, _ = self.get_tv_dest_path(meta_info)
            if self._tv_category_flag:
                return os.path.join(dest, meta_info.category, dir_name, season_name)
            else:
                return os.path.join(dest, dir_name, season_name)

    def get_no_exists_medias(self, meta_info, season=None, total_num=None):
        """
        根据媒体库目录结构，判断媒体是否存在
        :param meta_info: 已识别的媒体信息
        :param season: 季号，数字，剧集时需要
        :param total_num: 该季总集数，剧集时需要
        :return: 如果是电影返回已存在的电影清单：title、year，如果是剧集，则返回不存在的集的清单
        """
        if meta_info.type == MediaType.MOVIE:
            dir_name, _ = self.get_moive_dest_path(meta_info)
            for dest_path in self._movie_path:
                fav_path = os.path.join(dest_path, RMT_FAVTYPE, dir_name)
                fav_files = PathUtils.get_dir_files(fav_path, RMT_MEDIAEXT)
                if self._movie_category_flag:
                    dest_path = os.path.join(dest_path, meta_info.category, dir_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name)
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                if len(files) > 0 or len(fav_files) > 0:
                    return [{"title": meta_info.title, "year": meta_info.year}]
            return []
        else:
            dir_name, season_name, _ = self.get_tv_dest_path(meta_info)
            if not season or not total_num:
                return []
            if meta_info.type == MediaType.ANIME:
                dest_paths = self._anime_path
                category_flag = self._anime_category_flag
            else:
                dest_paths = self._tv_path
                category_flag = self._tv_category_flag
            total_episodes = list(range(1, total_num + 1))
            exists_episodes = []
            for dest_path in dest_paths:
                if category_flag:
                    dest_path = os.path.join(dest_path, meta_info.category, dir_name, season_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name, season_name)
                if not os.path.exists(dest_path):
                    continue
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                for file in files:
                    file_meta_info = meta_info(title=os.path.basename(file))
                    if not file_meta_info.get_season_list() or not file_meta_info.get_episode_list():
                        continue
                    if file_meta_info.get_name() != meta_info.title:
                        continue
                    if not file_meta_info.is_in_season(season):
                        continue
                    exists_episodes = list(set(exists_episodes).union(set(file_meta_info.get_episode_list())))
            return list(set(total_episodes).difference(set(exists_episodes)))

    def get_best_target_path(self, mtype, in_path=None, size=0):
        """
        查询一个最好的目录返回，有in_path时找与in_path同路径的，没有in_path时，顺序查找1个符合大小要求的，没有in_path和size时，返回第1个
        :param mtype: 媒体类型：电影、电视剧、动漫
        :param in_path: 源目录
        :param size: 文件大小
        """
        if not mtype:
            return None
        if mtype == MediaType.MOVIE:
            dest_paths = self._movie_path
        elif mtype == MediaType.TV:
            dest_paths = self._tv_path
        else:
            dest_paths = self._anime_path
        if not dest_paths:
            return None
        if not isinstance(dest_paths, list):
            return dest_paths
        if isinstance(dest_paths, list) and len(dest_paths) == 1:
            return dest_paths[0]
        if in_path:
            max_return_path = None
            max_path_len = 0
            for dest_path in dest_paths:
                try:
                    path_len = len(os.path.commonpath([in_path, dest_path]))
                    if path_len > max_path_len:
                        max_path_len = path_len
                        max_return_path = dest_path
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
            if max_return_path:
                return max_return_path
        if size:
            for path in dest_paths:
                if SystemUtils.get_free_space(path) > NumberUtils.get_size_gb(size):
                    return path
        return dest_paths[0]

    def _get_best_unknown_path(self, in_path):
        """
        查找最合适的unknown目录
        :param in_path: 源目录
        """
        if not self._unknown_path:
            return None
        for unknown_path in self._unknown_path:
            if os.path.commonpath([in_path, unknown_path]) not in ["/", "\\"]:
                return unknown_path
        return self._unknown_path[0]

    def link_sync_file(self, src_path, in_file, target_dir, operation):
        """
        对文件做纯链接处理，不做识别重命名，则监控模块调用
        :param : 来源渠道
        :param src_path: 源目录
        :param in_file: 源文件
        :param target_dir: 目的目录
        :param operation: 明确的转移方式
        """
        new_file = in_file.replace(src_path, target_dir)
        new_file_list, msg = self.check_ignore(file_list=[new_file])
        if not new_file_list:
            return 0, msg
        else:
            new_file = new_file_list[0]
        new_dir = os.path.dirname(new_file)
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)
        try:
            self._engine._execute(in_file, new_file, operation)
            return 0, ""
        except Exception as e:
            log.error(f"【Rmt】link_sync_file 失败：{e}")
            return 1, str(e)

    def get_format_dict(self, media):
        """
        根据媒体信息，返回Format字典
        """
        if not media:
            return {}
        episode_title = self.media.get_episode_title(media)
        en_title = self.media.get_tmdb_en_title(media)
        media_format_dict = {
            "title": StringUtils.clear_file_name(media.title),
            "en_title": StringUtils.clear_file_name(en_title),
            "original_name": StringUtils.clear_file_name(os.path.splitext(media.org_string or "")[0]),
            "rev_name": StringUtils.clear_file_name(os.path.splitext(media.rev_string or "")[0]),
            "original_title": StringUtils.clear_file_name(media.original_title),
            "name": StringUtils.clear_file_name(media.get_name()),
            "year": media.year,
            "edition": media.get_edtion_string() or None,
            "videoFormat": media.resource_pix,
            "releaseGroup": media.resource_team,
            "customization": media.customization,
            "effect": media.resource_effect,
            "videoCodec": media.video_encode,
            "audioCodec": media.audio_encode,
            "tmdbid": media.tmdb_id,
            "imdbid": media.imdb_id,
            "season": media.get_season_seq(),
            "episode": media.get_episode_seqs(),
            "episode_title": StringUtils.clear_file_name(episode_title),
            "season_episode": f"{media.get_season_item()}{media.get_episode_items()}",
            "part": media.part,
        }
        for i in media_format_dict:
            if not media_format_dict[i]:
                media_format_dict[i] = "\t"
        return media_format_dict

    def get_moive_dest_path(self, media_info):
        """
        计算电影文件路径
        :return: 电影目录、电影名称
        """
        format_dict = self.get_format_dict(media_info)
        dir_name = re.sub(r"[-_\s.]*\t", "", self._movie_dir_rmt_format.format(**format_dict))
        file_name = re.sub(r"[-_\s.]*\t", "", self._movie_file_rmt_format.format(**format_dict))
        return dir_name, file_name

    def get_tv_dest_path(self, media_info):
        """
        计算电视剧文件路径
        :return: 电视剧目录、季目录、集名称
        """
        format_dict = self.get_format_dict(media_info)
        dir_name = re.sub(r"[-_\s.]*\t", "", self._tv_dir_rmt_format.format(**format_dict))
        season_name = re.sub(r"[-_\s.]*\t", "", self._tv_season_rmt_format.format(**format_dict))
        file_name = re.sub(r"[-_\s.]*\t", "", self._tv_file_rmt_format.format(**format_dict))
        return dir_name, season_name, file_name

    def check_ignore(self, file_list):
        """
        检查过滤文件列表中忽略项目
        :param file_list: 文件路径列表
        """
        if not file_list:
            return [], ""
        ignored_paths = self._ignored_paths
        if ignored_paths:
            try:
                for file in file_list[:]:
                    if re.findall(ignored_paths, os.path.dirname(file)):
                        log.info(f"【Rmt】{file} 文件路径含转移忽略词，已忽略转移")
                        file_list.remove(file)
                if not file_list:
                    return [], "排除文件路径转移忽略词后，没有新文件需要处理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"【Rmt】文件路径转移忽略词设置有误：{str(err)}")

        ignored_files = self._ignored_files
        if ignored_files:
            try:
                for file in file_list[:]:
                    if re.findall(ignored_files, os.path.basename(file)):
                        log.info(f"【Rmt】{file} 文件名包含转移忽略词，已忽略转移")
                        file_list.remove(file)
                if not file_list:
                    return [], "排除文件名转移忽略词后，没有新文件需要处理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"【Rmt】文件名转移忽略词设置有误：{str(err)}")

        return file_list, ""

    def transfer_media(
        self,
        in_from,
        in_path,
        operation=None,
        files=None,
        target_dir=None,
        unknown_dir=None,
        tmdb_info=None,
        media_type=None,
        season=None,
        episode=None,
        min_filesize=None,
        udf_flag=False,
        root_path=False,
        dst_backend=None,
    ):
        """
        识别并转移一个文件、多个文件或者目录
        """
        if not in_path or not os.path.exists(in_path):
            return self._finish_transfer(False, f"文件转移失败，目录或文件不存在：{in_path}")

        if not operation:
            operation = self._default_operation

        self.progress.start(ProgressKey.FileTransfer)
        assert operation is not None
        log.info(f"【Rmt】开始处理：{in_path}，转移方式：{operation}")

        episode = episode if episode else (None, False)

        # ---------- 阶段1：发现文件 ----------
        bluray_disk_dir, file_list = self._discover_files(in_path, files, episode, min_filesize)
        if file_list is None:
            return self._finish_transfer(False, "输入路径错误")
        if not file_list:
            return self._finish_transfer(
                bluray_disk_dir is not None, "目录下未找到媒体文件" if bluray_disk_dir is None else ""
            )

        # ---------- 阶段2：过滤 ----------
        file_list, msg = self.check_ignore(file_list=file_list)
        if not file_list:
            return self._finish_transfer(True, msg)

        if in_from == SyncType.MON:
            file_list = list(filter(self.transfer_repo.is_transfer_notin_blacklist, file_list))
            if not file_list:
                log.info("【Rmt】所有文件均已成功转移过")
                return self._finish_transfer(True, "没有新文件需要处理")

        # ---------- 阶段3：查下载记录 + 批量识别 ----------
        if not tmdb_info:
            tmdb_info, media_type = self._lookup_download_record(in_path)

        medias = self.media.get_media_info_on_files(file_list, tmdb_info, media_type, season, episode[0])
        if not medias:
            return self._finish_transfer(False, "搜索媒体信息出错")

        self.progress.update(ptype=ProgressKey.FileTransfer, text=f"共 {len(medias)} 个文件需要处理...")

        # ---------- 阶段4：逐个文件转移 ----------
        result = self._transfer_files_loop(
            medias,
            in_from,
            in_path,
            operation,
            target_dir,
            unknown_dir,
            bluray_disk_dir,
            episode,
            udf_flag,
            dst_backend,
        )

        # ---------- 阶段5：后处理 ----------
        return self._transfer_post_process(result, in_from, in_path, operation, root_path)

    # ---------- 转移流水线私有方法 ----------

    def _finish_transfer(self, status, message):
        self.progress.update(
            ptype=ProgressKey.FileTransfer, value=100, text=f"转移{'成功' if status else '失败'}：{message}！"
        )
        self.progress.end(ProgressKey.FileTransfer)
        return status, message

    def _discover_files(self, in_path, files, episode, min_filesize):
        """发现待处理文件列表，返回 (bluray_disk_dir, file_list)"""
        bluray_disk_dir = None
        if not files:
            if os.path.isdir(in_path):
                if PathUtils.is_invalid_path(in_path):
                    return None, None
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info(f"【Rmt】当前为蓝光原盘文件夹：{str(in_path)}")
                else:
                    now_filesize = self._min_filesize
                    if str(min_filesize or "0") != "0":
                        ms_str = str(min_filesize)
                        if ms_str.isdigit():
                            now_filesize = int(ms_str) * 1024 * 1024
                    file_list = PathUtils.get_dir_files(
                        in_path=in_path, episode_format=episode[0], exts=RMT_MEDIAEXT, filesize=now_filesize
                    )
                    if not file_list:
                        log.warn(
                            f"【Rmt】{in_path} 目录下未找到媒体文件，最小文件大小限制为 {StringUtils.str_filesize(now_filesize)}"
                        )
            else:
                if os.path.splitext(in_path)[-1].lower() not in RMT_MEDIAEXT:
                    log.warn(f"【Rmt】不支持的媒体文件格式，不处理：{in_path}")
                    return None, []
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                else:
                    file_list = [in_path]
        else:
            file_list = files
        return bluray_disk_dir, file_list

    def _lookup_download_record(self, in_path):
        download_info = self.download_repo.get_download_history_by_path(in_path)
        if not download_info and os.path.isfile(in_path):
            download_info = self.download_repo.get_download_history_by_path(os.path.dirname(in_path))
        if download_info and str(download_info.TMDBID or ""):
            log.info(f"【Rmt】{in_path} 找到下载记录，TMDBID：{download_info.TMDBID}")
            media_type = MediaType.MOVIE if download_info.TYPE in MovieTypes else MediaType.TV
            return self.media.get_tmdb_info(mtype=media_type, tmdbid=download_info.TMDBID), media_type
        return None, None

    def _transfer_files_loop(
        self,
        medias,
        in_from,
        in_path,
        operation,
        target_dir,
        unknown_dir,
        bluray_disk_dir,
        episode,
        udf_flag,
        dst_backend,
    ):
        failed_count = 0
        alert_count = 0
        alert_messages = []
        total_count = 0
        message_medias = {}
        success_flag = True
        error_message = ""

        for file_item, media in medias.items():
            try:
                total_count += 1
                if not udf_flag and re.search(r"[./\s\[]+Sample[/\.\s\]]+", file_item, re.IGNORECASE):
                    log.warn(f"【Rmt】{file_item} 可能是预告片，跳过...")
                    continue

                file_name = os.path.basename(file_item)
                self.progress.update(
                    ptype=ProgressKey.FileTransfer,
                    value=round(total_count / len(medias) * 100) - (0.5 / len(medias) * 100),
                    text=f"正在处理：{file_name} ...",
                )

                reg_path = bluray_disk_dir if bluray_disk_dir else file_item

                if not media or not media.tmdb_info or not media.get_title_string():
                    fc, ac, am = self._handle_unrecognized_file(
                        file_item, reg_path, in_path, unknown_dir, operation, target_dir, udf_flag, alert_messages
                    )
                    failed_count += fc
                    alert_count += ac
                    alert_messages = am
                    if udf_flag:
                        return {
                            "total_count": total_count,
                            "failed_count": failed_count,
                            "alert_count": alert_count,
                            "alert_messages": alert_messages,
                            "message_medias": message_medias,
                            "success_flag": False,
                            "error_message": "无法识别媒体信息",
                        }
                    continue

                media.size = os.path.getsize(file_item)
                dist_path = target_dir or self.get_best_target_path(mtype=media.type, in_path=in_path, size=media.size)
                if not dist_path:
                    log.error("【Rmt】文件转移失败，目的路径不存在！")
                    failed_count += 1
                    alert_count += 1
                    alert_messages.append("目的路径不存在")
                    continue
                resolved_backend = dst_backend or self._resolve_dst_backend(dist_path, media.type)
                if not os.path.exists(dist_path) and not resolved_backend:
                    return {
                        "total_count": total_count,
                        "failed_count": failed_count,
                        "alert_count": alert_count,
                        "alert_messages": alert_messages,
                        "message_medias": message_medias,
                        "success_flag": False,
                        "error_message": f"目录不存在：{dist_path}",
                    }

                fc, ac, am, exist_filenum, new_file, ret_file_path, ret_dir_path = self._do_transfer_file(
                    file_item,
                    media,
                    dist_path,
                    bluray_disk_dir,
                    operation,
                    reg_path,
                    target_dir,
                    udf_flag,
                    alert_messages,
                    resolved_backend,
                )
                failed_count += fc
                alert_count += ac
                alert_messages = am
                if fc > 0:
                    continue

                file_ext = os.path.splitext(file_item)[-1]
                media.set_tmdb_info(
                    self.media.get_tmdb_info(mtype=media.type, tmdbid=media.tmdb_id, append_to_response="all")
                )
                out_path = new_file if not bluray_disk_dir else ret_dir_path

                self.transfer_repo.insert_transfer_history(
                    in_from=in_from,
                    rmt_mode=operation,
                    in_path=reg_path,
                    out_path=out_path or "",
                    dest=dist_path,
                    media_info=media,
                    dst_backend=dst_backend.id if hasattr(dst_backend, "id") else (dst_backend or "local"),
                )

                if isinstance(episode[1], bool) and episode[1]:
                    self.update_transfer_unknown_state(file_item)

                if media.type == MediaType.MOVIE:
                    self.message.send_transfer_movie_message(
                        in_from, media, exist_filenum, self._movie_category_flag or False
                    )
                else:
                    message_key = f"{media.get_title_string()}-{media.get_season_string()}"
                    if not message_medias.get(message_key):
                        message_medias[message_key] = media
                    if not message_medias[message_key].is_in_episode(media.get_episode_list()):
                        message_medias[message_key].total_episodes += media.total_episodes
                        message_medias[message_key].size += media.size

                self.scraper.gen_scraper_files(
                    media=media,
                    dir_path=ret_dir_path,
                    file_name=os.path.basename(ret_file_path or ret_dir_path or ""),
                    file_ext=file_ext,
                    dst_backend=dst_backend,
                )

                self.progress.update(
                    ptype=ProgressKey.FileTransfer,
                    value=round(total_count / len(medias) * 100),
                    text=f"{file_name} 转移完成",
                )
                if operation == "move":
                    sleep(round(random.uniform(0, 1), 1))

                self.eventmanager.send_event(
                    EventType.SubtitleDownload,
                    {
                        "media_info": media.to_dict(),
                        "file": ret_file_path,
                        "file_ext": file_ext,
                        "bluray": bool(bluray_disk_dir),
                    },
                )
                self.eventmanager.send_event(
                    EventType.TransferFinished,
                    {
                        "in_path": in_path,
                        "file": file_item,
                        "target_path": out_path,
                        "dest": dist_path,
                        "media_info": media.to_dict(),
                    },
                )

            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"【Rmt】文件转移时发生错误：{str(err)}")
                failed_count += 1
                success_flag = False
                if not error_message:
                    error_message = str(err)

        return {
            "total_count": total_count,
            "failed_count": failed_count,
            "alert_count": alert_count,
            "alert_messages": alert_messages,
            "message_medias": message_medias,
            "success_flag": success_flag,
            "error_message": error_message,
        }

    def _handle_unrecognized_file(
        self, file_item, reg_path, in_path, unknown_dir, operation, target_dir, udf_flag, alert_messages
    ):
        file_name = os.path.basename(file_item)
        error = "无法识别媒体信息"
        log.warn(f"【Rmt】{file_name} {error}！")
        self.progress.update(ptype=ProgressKey.FileTransfer, text=error)
        insert = self.transfer_repo.is_need_insert_transfer_unknown(reg_path)
        if insert:
            self.transfer_repo.insert_transfer_unknown(reg_path, target_dir, operation)
        if error not in alert_messages and insert:
            alert_messages = alert_messages + [error]
        if unknown_dir:
            log.warn(f"【Rmt】{file_name} 按原文件名转移到未识别目录：{unknown_dir}")
            new_file = os.path.join(unknown_dir, os.path.basename(file_item))
            self._engine.transfer(file_item, new_file, operation)
        elif self._unknown_path:
            p = self._get_best_unknown_path(in_path)
            if p:
                log.warn(f"【Rmt】{file_name} 按原文件名转移到未识别目录：{p}")
                new_file = os.path.join(p, os.path.basename(file_item))
                self._engine.transfer(file_item, new_file, operation)
        else:
            log.error(f"【Rmt】{file_name} {error}！")
        return 1, 1 if insert else 0, alert_messages

    def _do_transfer_file(
        self,
        file_item,
        media,
        dist_path,
        bluray_disk_dir,
        operation,
        reg_path,
        target_dir,
        udf_flag,
        alert_messages,
        dst_backend=None,
    ):
        dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path = self._is_media_exists(
            dist_path, media, dst_backend
        )
        file_ext = os.path.splitext(file_item)[-1]
        new_file = ret_file_path
        exist_filenum = 0

        if dir_exist_flag:
            if bluray_disk_dir:
                log.warn(f"【Rmt】蓝光原盘目录已存在：{ret_dir_path}")
                return 1, 0, alert_messages, 0, new_file, ret_file_path, ret_dir_path
            if file_exist_flag and ret_file_path:
                exist_filenum = 1
                if operation != "softlink":
                    orgin_size = os.path.getsize(ret_file_path)
                    if media.size > orgin_size and self._filesize_cover or udf_flag:
                        old = ret_file_path
                        base, _ = os.path.splitext(ret_file_path)
                        new_file = f"{base}{file_ext}"
                        log.info(f"【Rmt】文件 {old} 已存在，覆盖为 {new_file} ...")
                        self._engine.transfer(
                            file_item, new_file, operation, over_flag=True, old_file=old, dst_backend=dst_backend
                        )
                        return 0, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path
                    else:
                        log.warn(f"【Rmt】文件 {ret_file_path} 已存在")
                        return 1, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path
                else:
                    log.warn(f"【Rmt】文件 {ret_file_path} 已存在")
                    return 1, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path
        else:
            if not ret_dir_path:
                return self._record_fail(
                    file_item,
                    reg_path,
                    target_dir,
                    operation,
                    udf_flag,
                    alert_messages,
                    "识别失败，无法从文件名中识别出季集信息",
                )
            elif not dst_backend:
                os.makedirs(ret_dir_path)

        if bluray_disk_dir:
            if not ret_dir_path:
                return self._record_fail(
                    file_item,
                    reg_path,
                    target_dir,
                    operation,
                    udf_flag,
                    alert_messages,
                    "识别失败，无法获取蓝光目录路径",
                )
            self._engine.transfer_bluray_dir(file_item, ret_dir_path, operation)
        elif not ret_file_path:
            return self._record_fail(
                file_item,
                reg_path,
                target_dir,
                operation,
                udf_flag,
                alert_messages,
                "识别失败，无法从文件名中识别出集数",
            )
        else:
            ret_file_path = f"{ret_file_path}{file_ext}"
            new_file = ret_file_path
            self._engine.transfer(file_item, ret_file_path, operation, over_flag=False, dst_backend=dst_backend)
        return 0, 0, alert_messages, exist_filenum, new_file, ret_file_path, ret_dir_path

    def _record_fail(self, file_item, reg_path, target_dir, operation, udf_flag, alert_messages, msg):
        self.progress.update(ptype=ProgressKey.FileTransfer, text=msg)
        insert = self.transfer_repo.is_need_insert_transfer_unknown(reg_path)
        if insert:
            self.transfer_repo.insert_transfer_unknown(reg_path, target_dir, operation)
        if msg not in alert_messages and insert:
            alert_messages = alert_messages + [msg]
        return 1, 1 if insert else 0, alert_messages, 0, None, None, None

    def _transfer_post_process(self, result, in_from, in_path, operation, root_path):
        if result["message_medias"]:
            self.message.send_transfer_tv_message(result["message_medias"], in_from)

        total_count = result["total_count"]
        failed_count = result["failed_count"]
        alert_count = result["alert_count"]
        alert_messages = result["alert_messages"]
        success_flag = result["success_flag"]
        error_message = result["error_message"]

        log.info(f"【Rmt】{in_path} 处理完成，总数：{total_count}，失败：{failed_count}")
        if alert_count > 0:
            reason = "、".join(alert_messages)
            self.eventmanager.send_event(
                EventType.TransferFail, {"path": in_path, "count": alert_count, "reason": reason}
            )
            self.message.send_transfer_fail_message(in_path, alert_count, reason)
        elif failed_count == 0:
            if (
                operation == "move"
                and os.path.exists(in_path)
                and os.path.isdir(in_path)
                and not root_path
                and not PathUtils.get_dir_files(in_path=in_path, exts=RMT_MEDIAEXT)
                and not PathUtils.get_dir_files(in_path=in_path, exts=[".!qb", ".part"])
            ):
                log.info(f"【Rmt】目录下已无媒体文件，移动模式下删除目录：{in_path}")
                shutil.rmtree(in_path)
        return self._finish_transfer(success_flag, error_message)

    def transfer_manually(self, s_path, t_path, operation):
        """
        全量转移，用于使用命令调用
        :param s_path: 源目录
        :param t_path: 目的目录
        :param operation: 转移方式
        """
        if not s_path:
            return
        if not os.path.exists(s_path):
            print(f"【Rmt】源目录不存在：{s_path}")
            return
        if t_path:
            if not os.path.exists(t_path):
                print(f"【Rmt】目的目录不存在：{t_path}")
                return
        print(f"【Rmt】转移模式为：{operation}")
        print(f"【Rmt】正在转移以下目录中的全量文件：{s_path}")
        for path in PathUtils.get_dir_level1_medias(s_path, RMT_MEDIAEXT):
            if PathUtils.is_invalid_path(path):
                continue
            ret, ret_msg = self.transfer_media(
                in_from=SyncType.MAN, in_path=path, target_dir=t_path, operation=operation
            )
            if not ret:
                print(f"【Rmt】{path} 处理失败：{ret_msg}")

    def get_transfer_info_by(self, tmdbid, season=None, season_episode=None):
        """
        查询转移历史记录
        """
        return self.transfer_repo.get_transfer_info_by(tmdbid=tmdbid, season=season, season_episode=season_episode)

    def get_transfer_info_by_id(self, logid):
        """
        根据LogID查询转移历史记录
        """
        return self.transfer_repo.get_transfer_info_by_id(logid=logid)

    def get_transfer_history(self, search, page, rownum):
        """
        查询转移历史记录
        """
        return self.transfer_repo.get_transfer_history(search=search, page=page, rownum=rownum)

    def delete_transfer_log_by_id(self, logid):
        """
        删除转移历史记录
        """
        return self.transfer_repo.delete_transfer_log_by_id(logid=logid)

    def delete_history(self, logids, flag=None):
        """
        删除识别记录及文件
        """
        for logid in logids:
            transinfo = self.get_transfer_info_by_id(logid)
            if transinfo:
                self.delete_transfer_log_by_id(logid)
                source_path = transinfo.SOURCE_PATH
                source_filename = transinfo.SOURCE_FILENAME
                media_info = {
                    "type": transinfo.TYPE,
                    "category": transinfo.CATEGORY,
                    "title": transinfo.TITLE,
                    "year": transinfo.YEAR,
                    "tmdbid": transinfo.TMDBID,
                    "season_episode": transinfo.SEASON_EPISODE,
                }
                self.delete_transfer_blacklist(f"{source_path}/{source_filename}")
                dest = transinfo.DEST
                dest_path = transinfo.DEST_PATH
                dest_filename = transinfo.DEST_FILENAME
                if flag in ["del_source", "del_all"]:
                    del_flag, del_msg = self.delete_media_file(source_path, source_filename)
                    if not del_flag:
                        log.error(del_msg)
                    else:
                        log.info(del_msg)
                        from app.plugin_framework.event_compat import EventManager

                        EventManager().send_event(
                            EventType.SourceFileDeleted,
                            {"media_info": media_info, "path": source_path, "filename": source_filename},
                        )
                if flag in ["del_dest", "del_all"]:
                    if str(dest_path) and str(dest_filename):
                        del_flag, del_msg = self.delete_media_file(dest_path, dest_filename)
                        if not del_flag:
                            log.error(del_msg)
                        else:
                            log.info(del_msg)
                            from app.plugin_framework.event_compat import EventManager

                            EventManager().send_event(
                                EventType.LibraryFileDeleted,
                                {"media_info": media_info, "path": dest_path, "filename": dest_filename},
                            )
                    else:
                        mi = meta_info(title=str(source_filename or ""))
                        mi.title = str(transinfo.TITLE or "")
                        mi.category = str(transinfo.CATEGORY or "")
                        mi.year = str(transinfo.YEAR or "")
                        if str(transinfo.SEASON_EPISODE or ""):
                            mi.begin_season = int(str(transinfo.SEASON_EPISODE).replace("S", ""))
                        if MediaType.MOVIE.value == transinfo.TYPE:
                            mi.type = MediaType.MOVIE
                        else:
                            mi.type = MediaType.TV
                        dest_path = self.get_dest_path_by_info(dest=dest, meta_info=mi)
                        if dest_path and dest_path.find(mi.title or "") != -1:
                            rm_parent_dir = False
                            if not mi.get_season_list():
                                try:
                                    import shutil

                                    shutil.rmtree(dest_path)
                                    from app.plugin_framework.event_compat import EventManager

                                    EventManager().send_event(
                                        EventType.LibraryFileDeleted, {"media_info": media_info, "path": dest_path}
                                    )
                                except Exception as e:
                                    from app.utils import ExceptionUtils

                                    ExceptionUtils.exception_traceback(e)
                            elif not mi.get_episode_string():
                                try:
                                    import shutil

                                    shutil.rmtree(dest_path)
                                    from app.plugin_framework.event_compat import EventManager

                                    EventManager().send_event(
                                        EventType.LibraryFileDeleted, {"media_info": media_info, "path": dest_path}
                                    )
                                except Exception as e:
                                    from app.utils import ExceptionUtils

                                    ExceptionUtils.exception_traceback(e)
                                rm_parent_dir = True
                            else:
                                for dest_file in PathUtils.get_dir_files(dest_path):
                                    file_meta_info = meta_info(os.path.basename(dest_file))
                                    if file_meta_info.get_episode_list() and set(
                                        file_meta_info.get_episode_list()
                                    ).issubset(set(mi.get_episode_list())):
                                        try:
                                            os.remove(dest_file)
                                            from app.plugin_framework.event_compat import EventManager

                                            EventManager().send_event(
                                                EventType.LibraryFileDeleted,
                                                {
                                                    "media_info": media_info,
                                                    "path": os.path.dirname(dest_file),
                                                    "filename": os.path.basename(dest_file),
                                                },
                                            )
                                        except Exception as e:
                                            from app.utils import ExceptionUtils

                                            ExceptionUtils.exception_traceback(e)
                                rm_parent_dir = True
                            if rm_parent_dir and not PathUtils.get_dir_files(
                                os.path.dirname(dest_path), exts=RMT_MEDIAEXT
                            ):
                                try:
                                    import shutil

                                    shutil.rmtree(os.path.dirname(dest_path))
                                except Exception as e:
                                    from app.utils import ExceptionUtils

                                    ExceptionUtils.exception_traceback(e)

    def delete_media_file(self, filedir, filename, backend_id="local"):
        """
        删除媒体文件（统一使用存储后端接口）
        """
        try:
            # 清理路径尾部斜杠，避免 os.path.basename 返回空字符串
            file = os.path.join(filedir, filename).rstrip("/")
            filedir = os.path.dirname(file)
            filename = os.path.basename(file)

            # 安全检查
            if not filename:
                log.error(f"【Delete】文件名为空，原始路径={filedir}/{filename}")
                return False, "无效的文件路径"
            if not filedir or filedir in ("/", "\\"):
                return False, "不能删除根目录"
            if file == filedir:
                return False, "不能删除父目录"

            log.info(f"【Delete】准备删除：filedir={filedir}, filename={filename}, file={file}")

            backend = self._resolve_backend_by_id(backend_id)
            if not backend:
                return False, "无法解析存储后端"
            if not backend.exists(file):
                return False, "文件不存在"

            backend.remove(file, recursive=True)
            log.info(f"【Delete】删除成功：{file}")
            return True, "删除成功"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False, str(e)

    def _resolve_backend_by_id(self, backend_id: str):
        """根据 ID 解析存储后端（本地返回 LocalStorageBackend 实例）"""
        if not backend_id or backend_id == "local":
            return LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        repo = StorageBackendRepositoryAdapter()
        entity = repo.get_by_id(int(backend_id))
        if not entity:
            return None
        info = StorageBackendFactory.get_config_info(entity.type)
        if info:
            stype, cls = info
        else:
            stype, cls = StorageType.LOCAL, LocalStorageConfig
        config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
        for k, v in entity.config.items():
            if hasattr(config, k):
                setattr(config, k, v)
        return StorageBackendFactory.create(config)

    def delete_transfer(self):
        """
        删除转移历史记录
        """
        return self.transfer_repo.delete_transfer()

    def delete_transfer_unknown(self, tid):
        """
        删除未知转移记录
        """
        return self.transfer_repo.delete_transfer_unknown(tid=tid)

    def get_unknown_info_by_id(self, tid):
        """
        根据ID查询未知转移记录
        """
        return self.transfer_repo.get_unknown_info_by_id(tid=tid)

    def update_transfer_unknown_state(self, path):
        """
        更新未知转移记录状态
        """
        return self.transfer_repo.update_transfer_unknown_state(path=path)

    def delete_transfer_blacklist(self, path):
        """
        删除黑名单记录
        """
        return self.transfer_repo.delete_transfer_blacklist(path=path)

    def truncate_transfer_blacklist(self):
        """
        清空黑名单记录
        """
        return self.transfer_repo.truncate_transfer_blacklist()

    def get_transfer_statistics(self, days=30):
        """
        查询转移统计
        """
        return self.transfer_repo.get_transfer_statistics(days=days)

    def get_transfer_unknown_paths(self):
        """
        查询未知转移记录
        """
        return self.transfer_repo.get_transfer_unknown_paths()

    def get_transfer_unknown_paths_by_page(self, search, page, rownum):
        """
        查询未知转移记录
        """
        return self.transfer_repo.get_transfer_unknown_paths_by_page(search=search, page=page, rownum=rownum)

    def get_sync_backend_by_dest(self, dest: str) -> str:
        """根据目的目录查找对应同步配置的目标后端"""
        if not dest:
            return "local"
        try:
            for entity in self.sync_repo.get_all():
                if str(entity.dest or "") == dest:
                    return str(entity.dst_backend or "local") or "local"
        except Exception:
            pass
        return "local"
