"""TransferCleanupService - 转移后清理与删除逻辑."""

import os
import shutil

import log
from app.core.constants import RMT_MEDIAEXT
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.media import meta_info
from app.plugin_framework.event_compat import EventHandler
from app.storage import StorageBackendFactory
from app.storage.backends.base import StorageConfig, StorageType
from app.storage.backends.local import LocalStorageBackend
from app.storage.config_models import LocalStorageConfig
from app.utils import ExceptionUtils, PathUtils
from app.utils.types import EventType, MediaType
from app.di import container


class TransferCleanupService:
    """负责删除历史记录、媒体文件及关联目录清理."""

    def __init__(self, history_manager, path_resolver, media_service=None, message=None, eventmanager=None):
        self._history = history_manager
        self._path_resolver = path_resolver
        self._media = media_service
        self._message = message
        self._eventmanager = eventmanager or EventHandler

    def delete_media_file(self, filedir, filename, backend_id="local"):
        """删除媒体文件（统一使用存储后端接口）."""
        try:
            file = os.path.join(filedir, filename).rstrip("/")
            filedir = os.path.dirname(file)
            filename = os.path.basename(file)

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
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False, str(e)

    def _resolve_backend_by_id(self, backend_id: str):
        """根据 ID 解析存储后端（本地返回 LocalStorageBackend 实例）."""
        if not backend_id or backend_id == "local":
            return LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        repo = container.storage_backend_repo()
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

    def delete_history(self, logids, flag=None):
        """删除识别记录及文件."""
        for logid in logids:
            transinfo = self._history.get_transfer_info_by_id(logid)
            if transinfo:
                self._history.delete_transfer_log_by_id(logid)
                source_path = transinfo.SOURCE_PATH
                source_filename = transinfo.SOURCE_FILENAME
                media_info_dict = {
                    "type": transinfo.TYPE,
                    "category": transinfo.CATEGORY,
                    "title": transinfo.TITLE,
                    "year": transinfo.YEAR,
                    "tmdbid": transinfo.TMDBID,
                    "season_episode": transinfo.SEASON_EPISODE,
                }
                self._history.delete_transfer_blacklist(f"{source_path}/{source_filename}")
                dest = transinfo.DEST
                dest_path = transinfo.DEST_PATH
                dest_filename = transinfo.DEST_FILENAME
                if flag in ["del_source", "del_all"]:
                    del_flag, del_msg = self.delete_media_file(source_path, source_filename)
                    if not del_flag:
                        log.error(del_msg)
                    else:
                        log.info(del_msg)
                        self._eventmanager.send_event(
                            EventType.SourceFileDeleted,
                            {"media_info": media_info_dict, "path": source_path, "filename": source_filename},
                        )
                if flag in ["del_dest", "del_all"]:
                    if str(dest_path) and str(dest_filename):
                        del_flag, del_msg = self.delete_media_file(dest_path, dest_filename)
                        if not del_flag:
                            log.error(del_msg)
                        else:
                            log.info(del_msg)
                            self._eventmanager.send_event(
                                EventType.LibraryFileDeleted,
                                {"media_info": media_info_dict, "path": dest_path, "filename": dest_filename},
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
                        dest_path = self._path_resolver.get_dest_path_by_info(
                            dest=dest, meta_info=mi, media_service=self._media
                        )
                        if dest_path and dest_path.find(mi.title or "") != -1:
                            rm_parent_dir = False
                            if not mi.get_season_list():
                                try:
                                    shutil.rmtree(dest_path)
                                    self._eventmanager.send_event(
                                        EventType.LibraryFileDeleted, {"media_info": media_info_dict, "path": dest_path}
                                    )
                                except Exception as e:
                                    ExceptionUtils.exception_traceback(e)
                            elif not mi.get_episode_string():
                                try:
                                    shutil.rmtree(dest_path)
                                    self._eventmanager.send_event(
                                        EventType.LibraryFileDeleted, {"media_info": media_info_dict, "path": dest_path}
                                    )
                                except Exception as e:
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
                                            self._eventmanager.send_event(
                                                EventType.LibraryFileDeleted,
                                                {
                                                    "media_info": media_info_dict,
                                                    "path": os.path.dirname(dest_file),
                                                    "filename": os.path.basename(dest_file),
                                                },
                                            )
                                        except Exception as e:
                                            ExceptionUtils.exception_traceback(e)
                                rm_parent_dir = True
                            if rm_parent_dir and not PathUtils.get_dir_files(
                                os.path.dirname(dest_path), exts=RMT_MEDIAEXT
                            ):
                                try:
                                    shutil.rmtree(os.path.dirname(dest_path))
                                except Exception as e:
                                    ExceptionUtils.exception_traceback(e)
