"""TransferCleanupService - 转移后清理与删除逻辑."""

import os

import log
from app.core.constants import RMT_MEDIAEXT
from app.core.exceptions import (
    ResourceNotFoundError,
    ServiceError,
    ValidationError,
)
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.events import Event
from app.events.bus import EventBus
from app.events.constants import LIBRARY_FILE_DELETED, MEDIA_SOURCE_DELETED
from app.media import meta_info
from app.storage import StorageBackendFactory
from app.storage.backends.base import StorageConfig, StorageType
from app.storage.backends.local import LocalStorageBackend
from app.storage.config_models import LocalStorageConfig
from app.utils import ExceptionUtils, PathUtils
from app.domain.mediatypes import MediaType


class TransferCleanupService:
    """负责删除历史记录、媒体文件及关联目录清理."""

    def __init__(
        self,
        history_manager,
        path_resolver,
        media_service,
        message,
        event_bus: EventBus,
        storage_backend_repo: StorageBackendRepositoryAdapter | None = None,
    ):
        self._history = history_manager
        self._path_resolver = path_resolver
        self._media = media_service
        self._storage_backend_repo = storage_backend_repo or StorageBackendRepositoryAdapter()
        self._message = message
        self._event_bus = event_bus

    def delete_media_file(self, filedir, filename, backend_id="local") -> None:
        """删除媒体文件（统一使用存储后端接口），失败时抛出异常."""
        file = os.path.join(filedir, filename).rstrip("/")
        filedir = os.path.dirname(file)
        filename = os.path.basename(file)

        if not filename:
            raise ValidationError("无效的文件路径")
        if not filedir or filedir in ("/", "\\"):
            raise ValidationError("不能删除根目录")
        if file == filedir:
            raise ValidationError("不能删除父目录")

        log.info(f"[Delete]准备删除：filedir={filedir}, filename={filename}, file={file}")

        backend = self._resolve_backend_by_id(backend_id)
        if not backend:
            raise ServiceError("无法解析存储后端")
        if not backend.exists(file):
            raise ResourceNotFoundError("文件不存在")

        backend.remove(file, recursive=True)
        log.info(f"[Delete]删除成功：{file}")

    def _resolve_backend_by_id(self, backend_id: str):
        """根据 ID 解析存储后端（本地返回 LocalStorageBackend 实例）."""
        if not backend_id or backend_id == "local":
            return LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        entity = self._storage_backend_repo.get_by_id(int(backend_id))
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

    def _is_safe_delete_path(self, path: str, title: str | None = None) -> bool:
        """检查路径是否可以安全删除：必须在媒体库范围内且不是根目录."""
        if not path or path in ("/", "\\", "//"):
            return False
        if not self._path_resolver.is_target_dir_path(path):
            log.warn(f"[Delete]路径 {path} 不在媒体库范围内，跳过删除")
            return False
        if title and title not in path:
            log.warn(f"[Delete]路径 {path} 不包含媒体标题 {title}，跳过删除")
            return False
        return True

    def _remove_dir_with_backend(self, path: str, backend_id: str = "local") -> None:
        """使用存储后端安全删除目录（支持 SMB/WebDAV 等远程存储）."""
        if not self._is_safe_delete_path(path):
            return
        backend = self._resolve_backend_by_id(backend_id)
        if not backend:
            log.error(f"[Delete]无法解析存储后端 {backend_id}")
            return
        if not backend.exists(path):
            log.warn(f"[Delete]路径不存在，跳过删除: {path}")
            return
        try:
            backend.remove(path, recursive=True)
            log.info(f"[Delete]目录删除成功: {path}")
        except Exception as e:
            log.error(f"[Delete]删除目录失败 {path}: {e}")
            raise

    def _has_media_files(self, path: str, backend_id: str = "local") -> bool:
        """检查目录中是否还存在媒体文件，支持本地和远程存储."""
        if not path:
            return False
        if backend_id == "local":
            return bool(PathUtils.get_dir_files(in_path=path, exts=RMT_MEDIAEXT))
        backend = self._resolve_backend_by_id(backend_id)
        if not backend:
            return False
        try:
            for finfo in backend.list_dir(path):
                if not finfo.is_dir:
                    ext = os.path.splitext(finfo.path)[1].lower()
                    if ext in RMT_MEDIAEXT:
                        return True
            return False
        except Exception:
            return False

    def delete_history(self, logids, flag=None):
        """删除识别记录及文件."""
        for logid in logids:
            transinfo = self._history.get_transfer_info_by_id(logid)
            if not transinfo:
                continue
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
            dst_backend = getattr(transinfo, "DST_BACKEND", None) or "local"
            if flag in ["del_source", "del_all"]:
                try:
                    self.delete_media_file(source_path, source_filename)
                    self._event_bus.publish(
                        Event(
                            event_type=MEDIA_SOURCE_DELETED,
                            payload={"media_info": media_info_dict, "path": source_path, "filename": source_filename},
                        )
                    )
                except (ServiceError, ResourceNotFoundError, ValidationError) as e:
                    log.error(f"[Delete]删除源文件失败: {e.message}")
            if flag in ["del_dest", "del_all"]:
                if str(dest_path) and str(dest_filename):
                    try:
                        self.delete_media_file(dest_path, dest_filename, backend_id=dst_backend)
                        self._event_bus.publish(
                            Event(
                                event_type=LIBRARY_FILE_DELETED,
                                payload={"media_info": media_info_dict, "path": dest_path, "filename": dest_filename},
                            )
                        )
                    except (ServiceError, ResourceNotFoundError, ValidationError) as e:
                        log.error(f"[Delete]删除目标文件失败: {e.message}")
                else:
                    mi = meta_info(title=str(source_filename or ""))
                    mi.title = str(transinfo.TITLE or "")
                    mi.category = str(transinfo.CATEGORY or "")
                    mi.year = str(transinfo.YEAR or "")
                    if str(transinfo.SEASON_EPISODE or ""):
                        mi.begin_season = int(str(transinfo.SEASON_EPISODE).replace("S", ""))
                    if MediaType.from_string(transinfo.TYPE) == MediaType.MOVIE:
                        mi.type = MediaType.MOVIE
                    else:
                        mi.type = MediaType.TV
                    dest_path = self._path_resolver.get_dest_path_by_info(
                        dest=dest, meta_info=mi, media_service=self._media
                    )
                    if self._is_safe_delete_path(dest_path, mi.title):
                        rm_parent_dir = False
                        if not mi.get_season_list():
                            try:
                                self._remove_dir_with_backend(dest_path, dst_backend)
                                self._event_bus.publish(
                                    Event(
                                        event_type=LIBRARY_FILE_DELETED,
                                        payload={"media_info": media_info_dict, "path": dest_path},
                                    )
                                )
                            except Exception as e:
                                ExceptionUtils.exception_traceback(e)
                        elif not mi.get_episode_string():
                            try:
                                self._remove_dir_with_backend(dest_path, dst_backend)
                                self._event_bus.publish(
                                    Event(
                                        event_type=LIBRARY_FILE_DELETED,
                                        payload={"media_info": media_info_dict, "path": dest_path},
                                    )
                                )
                            except Exception as e:
                                ExceptionUtils.exception_traceback(e)
                            rm_parent_dir = True
                        else:
                            backend = self._resolve_backend_by_id(dst_backend)
                            if backend:
                                try:
                                    for finfo in backend.list_dir(dest_path):
                                        if finfo.is_dir:
                                            continue
                                        file_meta_info = meta_info(os.path.basename(finfo.path))
                                        if file_meta_info.get_episode_list() and set(
                                            file_meta_info.get_episode_list()
                                        ).issubset(set(mi.get_episode_list())):
                                            try:
                                                backend.remove(finfo.path)
                                                self._event_bus.publish(
                                                    Event(
                                                        event_type=LIBRARY_FILE_DELETED,
                                                        payload={
                                                            "media_info": media_info_dict,
                                                            "path": os.path.dirname(finfo.path),
                                                            "filename": os.path.basename(finfo.path),
                                                        },
                                                    )
                                                )
                                            except Exception as e:
                                                ExceptionUtils.exception_traceback(e)
                                except Exception as e:
                                    log.error(f"[Delete]无法列出远程目录 {dest_path}: {e}")
                                    ExceptionUtils.exception_traceback(e)
                            rm_parent_dir = True
                        if rm_parent_dir:
                            parent_path = os.path.dirname(dest_path)
                            if self._is_safe_delete_path(parent_path, mi.title) and not self._has_media_files(
                                parent_path, dst_backend
                            ):
                                try:
                                    self._remove_dir_with_backend(parent_path, dst_backend)
                                except Exception as e:
                                    ExceptionUtils.exception_traceback(e)
