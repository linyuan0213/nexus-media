"""统一转移管道 — 目录同步与下载器完成转移的统一入口。"""

import os
from typing import Any

import log
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.db.repositories.transfer_repo_adapter import TransferBlacklistRepositoryAdapter
from app.domain.entities.transfer_task import SourceType, TransferTask
from app.media.scraper import Scraper
from app.services.filetransfer_service import FileTransferService
from app.storage.backends.base import StorageBackend, StorageType
from app.storage.config_models import LocalStorageConfig
from app.storage.factory import StorageBackendFactory
from app.utils.types import SyncType


class TransferPipeline:
    """
    统一转移管道。

    无论是目录同步（SyncEngine）还是下载器完成（DownloaderCore），
    文件整理都通过本管道执行，确保行为一致：
    1. 文件发现
    2. 媒体识别
    3. 目标路径 + 后端解析
    4. 执行转移
    5. 刮削元数据
    6. 写入黑名单（避免重复处理）
    7. 来源特定后处理（如下载器删种）
    """

    def __init__(
        self,
        filetransfer: FileTransferService | None = None,
        scraper: Scraper | None = None,
        blacklist_repo: TransferBlacklistRepositoryAdapter | None = None,
        backend_repo: StorageBackendRepositoryAdapter | None = None,
    ):
        self._filetransfer = filetransfer or FileTransferService()
        self._scraper = scraper or Scraper()
        self._blacklist = blacklist_repo or TransferBlacklistRepositoryAdapter()
        self._backend_repo = backend_repo or StorageBackendRepositoryAdapter()

    def process(self, task: TransferTask) -> tuple[bool, str]:
        """
        执行单个转移任务。

        :return: (success, message)
        """
        if not task.file_paths:
            return False, "没有待处理的文件"

        # ---------- 1. 解析目标后端 ----------
        dst_backend = self._resolve_backend(task.dst_backend_id)

        # ---------- 2. 逐个文件处理 ----------
        total_success = True
        messages: list[str] = []

        for file_path in task.file_paths:
            try:
                success, msg = self._process_single(file_path, task, dst_backend)
                if not success:
                    total_success = False
                    messages.append(msg)
            except Exception as e:
                total_success = False
                messages.append(str(e))
                log.error(f"【Pipeline】处理失败：{file_path}，{e}")

        final_msg = "; ".join(messages) if messages else "处理完成"

        # ---------- 3. 来源特定后处理 ----------
        if task.post_process:
            try:
                task.post_process(task, total_success, final_msg)
            except Exception as e:
                log.error(f"【Pipeline】后处理失败：{e}")

        return total_success, final_msg

    def _process_single(
        self, file_path: str, task: TransferTask, dst_backend: StorageBackend | None
    ) -> tuple[bool, str]:
        """处理单个文件/目录。"""
        # 根据来源类型映射 in_from
        in_from = self._map_source_type(task.source_type, task.source_id)

        # 调用 FileTransferService 执行转移
        success, msg = self._filetransfer.transfer_media(
            in_from=in_from,
            in_path=file_path,
            operation=task.operation,
            target_dir=task.target_dir,
            unknown_dir=task.unknown_dir,
            tmdb_info=task.tmdb_info,
            media_type=task.media_type,
            season=task.season,
            episode=task.episode,
            dst_backend=dst_backend,
        )

        if not success:
            return False, msg

        # ---------- 写入黑名单（所有来源统一） ----------
        self._blacklist.insert(file_path)

        # ---------- 刮削（如果目标路径是媒体库） ----------
        self._scrape_after_transfer(file_path, task, dst_backend)

        return True, msg

    def _scrape_after_transfer(self, file_path: str, task: TransferTask, dst_backend: StorageBackend | None) -> None:
        """转移成功后触发刮削。"""
        # 确定刮削目标路径
        scrape_path = task.target_dir or file_path
        if os.path.isfile(scrape_path):
            scrape_path = os.path.dirname(scrape_path)

        # 如果目标路径不是媒体库路径，跳过刮削
        if not self._is_media_library_path(scrape_path):
            return

        try:
            self._scraper.folder_scraper(
                path=scrape_path,
                mode="force_all",
                dst_backend=dst_backend,
            )
            log.info(f"【Pipeline】刮削完成：{scrape_path}")
        except Exception as e:
            log.error(f"【Pipeline】刮削失败：{scrape_path}，{e}")

    def _is_media_library_path(self, path: str) -> bool:
        """检查路径是否属于媒体库。"""
        if not path:
            return False
        from config import Config

        media = Config().get_config("media")
        if not media:
            return False
        all_paths = []
        for key in ("movie_path", "tv_path", "anime_path"):
            val = media.get(key)
            if val:
                if isinstance(val, list):
                    all_paths.extend(val)
                else:
                    all_paths.append(val)
        norm = path.rstrip("/") + "/"
        for lib_path in all_paths:
            if norm.startswith(lib_path.rstrip("/") + "/"):
                return True
        return False

    def _resolve_backend(self, backend_id: str) -> StorageBackend | None:
        """根据 backend_id 解析存储后端。"""
        if not backend_id or backend_id == "local":
            return None
        entity = self._backend_repo.get_by_id(int(backend_id))
        if not entity:
            log.warn(f"【Pipeline】未找到后端：{backend_id}")
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

    @staticmethod
    def _map_source_type(source_type: SourceType, source_id: str) -> Any:
        """将 SourceType 映射为 FileTransferService 的 in_from 值。"""
        if source_type == SourceType.DIRECTORY:
            return SyncType.MON
        if source_type == SourceType.DOWNLOADER:
            return source_id or "downloader"
        return SyncType.MAN
