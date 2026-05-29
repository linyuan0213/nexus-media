"""目录同步引擎。"""

import os
import threading
import traceback
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

import log
from app.core.constants import RMT_MEDIAEXT
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.db.repositories.transfer_repo_adapter import TransferHistoryRepositoryAdapter
from app.domain.entities.transfer_task import SourceType, TransferTask
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.services.transfer_pipeline import TransferPipeline
from app.storage.backends.base import StorageConfig, StorageType
from app.storage.backends.local import LocalStorageBackend
from app.storage.config_models import LocalStorageConfig
from app.storage.factory import StorageBackendFactory
from app.utils import PathUtils
from app.di import container

_synced_lock = threading.Lock()
_observer_lock = threading.Lock()


class FileMonitorHandler(FileSystemEventHandler):
    def __init__(self, monpath: str, engine: "SyncEngine"):
        super().__init__()
        self._watch_path = monpath
        self._engine = engine

    def on_created(self, event):
        self._engine.on_file_event(str(event.src_path))

    def on_moved(self, event):
        self._engine.on_file_event(str(event.dest_path))


class SyncPathConfig:
    def __init__(self, row: Any):
        self.id = str(row.ID)
        self.source = row.SOURCE or ""
        self.dest = row.DEST or ""
        self.unknown = row.UNKNOWN or ""
        self.operation = row.OPERATION or "copy"
        self.src_backend_id = row.SRC_BACKEND or "local"
        self.dst_backend_id = row.DST_BACKEND or "local"
        self.rename = bool(row.RENAME)
        self.compatibility = bool(row.COMPATIBILITY)
        self.enabled = bool(row.ENABLED)


class SyncEngine:
    def __init__(self):
        self._transfer = container.transfer_engine()
        self._pipeline = TransferPipeline()
        self._sync_repo = container.sync_path_repo()
        self._history_repo = TransferHistoryRepositoryAdapter()
        self._backend_repo = container.storage_backend_repo()
        self._configs: dict[str, SyncPathConfig] = {}
        self._monitor_ids: list[str] = []
        self._observers: list = []
        self._synced_files: list[str] = []
        self._reload()

    def init(self) -> None:
        self._reload()
        self._start()

    def _resolve_backend(self, backend_id: str):
        if backend_id == "local":
            return LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        entity = self._backend_repo.get_by_id(int(backend_id))
        if not entity:
            raise ValueError(f"未找到存储后端: {backend_id}")
        config = self._build_storage_config(entity)
        return StorageBackendFactory.create(config)

    def _build_storage_config(self, entity):
        info = StorageBackendFactory.get_config_info(entity.type)
        if info:
            stype, cls = info
        else:
            stype, cls = StorageType.LOCAL, LocalStorageConfig
        config = cls(id=str(entity.id), name=entity.name, type=stype, enabled=entity.enabled)
        for k, v in entity.config.items():
            if hasattr(config, k):
                setattr(config, k, v)
        return config

    def _reload(self) -> None:
        self._configs = {}
        self._monitor_ids = []
        for row in self._sync_repo.get_config_sync_paths():
            if not row:
                continue
            cfg = SyncPathConfig(row)
            log.info(
                f"[Sync]监控目录：{cfg.source} -> {cfg.dest} (操作={cfg.operation}, 目标后端={cfg.dst_backend_id})"
            )
            if not cfg.source or cfg.source in ("/", "\\"):
                log.warn(f"[Sync]跳过无效源目录: {cfg.source}")
                continue
            self._configs[cfg.id] = cfg
            if not cfg.enabled:
                log.info(f"[Sync]{cfg.source} 已关闭")
                continue
            try:
                src_backend = self._resolve_backend(cfg.src_backend_id)
                if src_backend.exists(cfg.source):
                    self._monitor_ids.append(cfg.id)
                else:
                    log.error(f"[Sync]{cfg.source} 目录不存在")
            except (ServiceError, RepositoryError, DomainError):
                raise
            except Exception as e:
                log.error(f"[Sync]检查 {cfg.source} 失败: {e}")

    @property
    def monitor_sync_path_ids(self) -> list[str]:
        return self._monitor_ids

    def get_sync_path_conf(self, sid: str) -> SyncPathConfig | None:
        return self._configs.get(sid)

    def get_all_sync_path_conf(self) -> dict[str, SyncPathConfig]:
        return self._configs

    def _start(self) -> None:
        self.stop()
        for sid in self._monitor_ids:
            cfg = self.get_sync_path_conf(sid)
            if not cfg:
                continue
            obs = PollingObserver(timeout=10) if cfg.compatibility else Observer(timeout=10)
            with _observer_lock:
                self._observers.append(obs)
            obs.schedule(FileMonitorHandler(cfg.source, self), path=cfg.source, recursive=True)
            obs.daemon = True
            obs.start()
            log.info(f"[Sync]{cfg.source} 监控已启动")

    def stop(self) -> None:
        with _observer_lock:
            for obs in self._observers:
                try:
                    obs.stop()
                    obs.join(timeout=5)
                except (ServiceError, RepositoryError, DomainError):
                    raise
                except Exception as e:
                    log.error(f"[Sync]停止监控异常: {e}")
            self._observers = []

    def on_file_event(self, event_path: str) -> None:
        with _synced_lock:
            if event_path in self._synced_files:
                return
            self._synced_files.append(event_path)

        try:
            cfg = self._find_config(event_path)
            if not cfg:
                return
            src_backend = self._resolve_backend(cfg.src_backend_id)
            if not src_backend.exists(event_path):
                return
            if PathUtils.is_invalid_path(event_path):
                return

            if not cfg.rename:
                self._do_link(event_path, cfg)
            else:
                self._do_transfer(event_path, cfg)
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            log.error(f"[Sync]处理失败：{e}\n{traceback.format_exc()}")

    def _find_config(self, event_path: str):
        for sid in self._monitor_ids:
            cfg = self.get_sync_path_conf(sid)
            if not cfg:
                continue
            if PathUtils.is_path_in_path(cfg.source, event_path):
                if PathUtils.is_path_in_path(cfg.dest, event_path):
                    log.error(f"[Sync]嵌套目录：{event_path}")
                    return None
                return cfg
        return None

    def _do_link(self, event_path: str, cfg: SyncPathConfig) -> None:
        if self._history_repo.is_sync_in_history(event_path, cfg.dest):
            return
        rel = os.path.relpath(event_path, cfg.source)
        dst = os.path.join(cfg.dest, rel)
        try:
            dst_backend = self._resolve_backend(cfg.dst_backend_id) if cfg.dst_backend_id != "local" else None
            self._transfer._execute(event_path, dst, cfg.operation, dst_backend)
            self._history_repo.insert_sync_history(event_path, cfg.source, cfg.dest)
            self._transfer._blacklist.insert(event_path)
            log.info(f"[Sync]{event_path} 同步完成")
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            log.error(f"[Sync]{event_path} 同步失败：{e}")

    def _do_transfer(self, event_path: str, cfg: SyncPathConfig) -> None:
        name = os.path.basename(event_path)
        if name.lower() != "index.bdmv":
            ext = os.path.splitext(name)[-1].lower()
            if ext not in RMT_MEDIAEXT:
                return
        task = TransferTask(
            source_type=SourceType.DIRECTORY,
            source_id=cfg.id,
            file_paths=[event_path],
            operation=cfg.operation,
            target_dir=cfg.dest,
            unknown_dir=cfg.unknown,
            dst_backend_id=cfg.dst_backend_id,
        )
        try:
            ret, msg = self._pipeline.process(task)
            if not ret:
                log.error(f"[Sync]{event_path} 转移失败：{msg}")
        except (ServiceError, RepositoryError, DomainError):
            raise
        except Exception as e:
            log.error(f"[Sync]{event_path} 转移异常：{e}")

    def transfer_sync(self, sid: str | None = None) -> None:
        lock_key = f"sync:transfer_sync:{sid or 'all'}"
        lock = get_lock_manager().create_lock(lock_key, ttl_seconds=300)
        acquired = lock.acquire()
        if not acquired:
            log.info(f"[Sync]transfer_sync({sid or 'all'}) 正在执行，跳过")
            return

        try:
            sids = [sid] if sid else self._monitor_ids
            for sid in sids:
                cfg = self.get_sync_path_conf(sid)
                if not cfg:
                    continue
                if not cfg.rename:
                    for f in PathUtils.get_dir_files(cfg.source):
                        self._do_link(f, cfg)
                else:
                    for p in PathUtils.get_dir_level1_medias(cfg.source, RMT_MEDIAEXT):
                        if PathUtils.is_invalid_path(p):
                            continue
                        self._do_transfer(p, cfg)
        finally:
            with _synced_lock:
                self._synced_files = []
            lock.release()

    def transfer_mon_files(self) -> None:
        self.transfer_sync()

    def delete_sync_path(self, sid: int) -> Any:
        ret = self._sync_repo.delete_config_sync_path(sid=sid)
        self.init()
        return ret

    def insert_sync_path(self, **kwargs) -> Any:
        ret = self._sync_repo.insert_config_sync_path(**kwargs)
        self.init()
        return ret

    def check_sync_paths(self, **kwargs) -> Any:
        ret = self._sync_repo.check_config_sync_paths(**kwargs)
        self.init()
        return ret

    def check_source(self, source: str | None = None, sid: str | None = None, dest: str | None = None) -> None:
        for cfg_id, cfg in self._configs.items():
            if sid and cfg_id != str(sid):
                continue
            if source and cfg.source == source:
                if dest and cfg.dest != dest:
                    continue
                self._sync_repo.check_config_sync_paths(sid=cfg_id, enabled=False)
                log.info(f"[Sync]关闭重复源目录：{cfg.source}")
