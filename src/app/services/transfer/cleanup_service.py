"""TransferCleanupService - 转移后清理与删除逻辑."""

import os
import re
import time

import log
from app.core.exceptions import (
    ResourceNotFoundError,
    ServiceError,
    ValidationError,
)
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.domain.media_types import ProviderMediaType
from app.events import Event
from app.events.bus import EventBus
from app.events.constants import LIBRARY_FILE_DELETED, MEDIA_SOURCE_DELETED
from app.events.payloads import LibraryFileDeletedPayload, MediaSourceDeletedPayload
from app.media import meta_info
from app.services.transfer.history_action_service import HistoryActionService
from app.services.transfer.media_file_deletion_service import MediaFileDeletionService
from app.utils import ExceptionUtils


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
        self._files = MediaFileDeletionService(path_resolver, self._storage_backend_repo)
        self._history_actions = HistoryActionService(history_manager, self._files, self.delete_history)

    # 兼容原有调用点：文件删除委托给独立服务
    def delete_media_file(self, filedir, filename, backend_id="local") -> None:
        return self._files.delete_media_file(filedir, filename, backend_id)

    def _resolve_backend_by_id(self, backend_id: str):
        return self._files.resolve_backend_by_id(backend_id)

    def _is_safe_delete_path(self, path: str, title: str | None = None) -> bool:
        return self._files.is_safe_delete_path(path, title)

    def _remove_dir_with_backend(self, path: str, backend_id: str = "local") -> None:
        return self._files.remove_dir_with_backend(path, backend_id)

    def _has_media_files(self, path: str, backend_id: str = "local") -> bool:
        return self._files.has_media_files(path, backend_id)

    def delete_records(self, logids: list[int]) -> list[dict]:
        return self._history_actions.delete_records(logids)

    def delete_record_files(self, logids: list[int], targets: list[str]) -> list[dict]:
        return self._history_actions.delete_record_files(logids, targets)

    def check_record_files(self, logids: list[int], targets: list[str] | None = None) -> list[dict]:
        return self._history_actions.check_record_files(logids, targets)

    def delete_history(self, logids, flag=None):
        """删除识别记录及文件."""
        if not logids:
            return

        # 批量预加载所有转移信息，减少数据库往返
        transinfos = []
        for logid in logids:
            transinfo = self._history.get_transfer_info_by_id(logid)
            if transinfo:
                transinfos.append(transinfo)

        # 只有“删除记录”才删历史；删除源/媒体库文件必须保留历史，
        # 否则同步任务会把仍在下载目录的源文件重新转移回来。
        delete_records = flag in (None, "", "del_log")
        if delete_records:
            self._history.delete_transfer_logs([t.ID for t in transinfos if hasattr(t, "ID")])

        for transinfo in transinfos:
            source_path = transinfo.SOURCE_PATH
            source_filename = transinfo.SOURCE_FILENAME
            media_info_dict = {
                "type": transinfo.media_type,
                "category": transinfo.CATEGORY,
                "title": transinfo.TITLE,
                "year": transinfo.YEAR,
                "tmdbid": transinfo.tmdb_id,
                "season_episode": transinfo.SEASON_EPISODE,
            }
            if delete_records:
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
                            payload=MediaSourceDeletedPayload(
                                media_info=media_info_dict, path=source_path, filename=source_filename
                            ),
                        )
                    )
                    self._history_actions.persist_file_state(
                        transinfo, "source", "deleted", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
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
                                payload=LibraryFileDeletedPayload(
                                    media_info=media_info_dict, path=dest_path, filename=dest_filename
                                ),
                            )
                        )
                    except (ServiceError, ResourceNotFoundError, ValidationError) as e:
                        log.error(f"[Delete]删除目标文件失败: {e.message}")
                else:
                    mi = meta_info(title=str(source_filename or ""))
                    mi.title = str(transinfo.TITLE or "")
                    mi.category = str(transinfo.CATEGORY or "")
                    mi.year = str(transinfo.YEAR or "")
                    season_str = str(transinfo.SEASON_EPISODE or "")
                    if season_str:
                        season_match = re.search(r"S(\d+)", season_str)
                        if season_match:
                            mi.begin_season = int(season_match.group(1))
                    if ProviderMediaType.from_value(transinfo.media_type) == ProviderMediaType.MOVIE:
                        mi.type = ProviderMediaType.MOVIE
                    else:
                        mi.type = ProviderMediaType.SERIES
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
                                        payload=LibraryFileDeletedPayload(
                                            media_info=media_info_dict, path=dest_path, filename=""
                                        ),
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
                                        payload=LibraryFileDeletedPayload(
                                            media_info=media_info_dict, path=dest_path, filename=""
                                        ),
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
