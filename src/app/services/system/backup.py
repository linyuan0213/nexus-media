"""系统备份服务：v2 原生 dump + Parquet，异步任务管理."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import log
from app.core.exceptions import DomainError, RepositoryError, ServiceError
from app.schemas.system import BackupRestoreResultDTO
from app.services.system.backup_v2 import create_backup, restore_backup
from app.utils import ExceptionUtils


class BackupRestoreService:
    """备份恢复业务服务，后台任务串行执行."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}
        self._tasks_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backup-task")

    @staticmethod
    def _task_view(task: dict) -> dict:
        return {key: value for key, value in task.items() if key != "file_path"}

    def _set_task(self, task_id: str, **values) -> None:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.update(values)
                task["updated_at"] = time.time()

    def _create_task(self, kind: str) -> str:
        task_id = uuid.uuid4().hex
        with self._tasks_lock:
            if len(self._tasks) > 30:
                finished = sorted(
                    (item for item in self._tasks.items() if item[1]["status"] in {"success", "failed"}),
                    key=lambda item: item[1]["updated_at"],
                )
                for old_id, _ in finished[: len(self._tasks) - 30]:
                    self._tasks.pop(old_id, None)
            self._tasks[task_id] = {
                "task_id": task_id,
                "type": kind,
                "status": "queued",
                "message": "等待执行",
                "file_name": "",
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        return task_id

    def start_backup(self) -> dict:
        task_id = self._create_task("backup")
        self._executor.submit(self._run_backup, task_id)
        task = self.get_task(task_id)
        assert task is not None
        return task

    def start_restore(self, filename: str) -> dict:
        task_id = self._create_task("restore")
        self._executor.submit(self._run_restore, task_id, filename)
        task = self.get_task(task_id)
        assert task is not None
        return task

    def get_task(self, task_id: str) -> dict | None:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            return self._task_view(task) if task else None

    def get_backup_file(self, task_id: str) -> Path | None:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task or task["type"] != "backup" or task["status"] != "success":
                return None
            path = Path(str(task.get("file_path") or ""))
            return path if path.is_file() else None

    def _run_backup(self, task_id: str) -> None:
        self._set_task(task_id, status="running", message="正在导出数据库并打包")
        try:
            zip_file = backup()
            if not zip_file:
                self._set_task(task_id, status="failed", message="创建备份失败")
                return
            self._set_task(
                task_id,
                status="success",
                message="备份完成",
                file_name=os.path.basename(zip_file),
                file_path=zip_file,
            )
        except Exception as exc:
            ExceptionUtils.exception_traceback(exc)
            self._set_task(task_id, status="failed", message=str(exc))

    def _run_restore(self, task_id: str, filename: str) -> None:
        self._set_task(task_id, status="running", message="正在恢复配置和数据库")
        try:
            result = self.restore_from_backup(filename)
            if result.success:
                self._set_task(task_id, status="success", message=result.message or "恢复成功")
            else:
                self._set_task(task_id, status="failed", message=result.message or "恢复失败")
        except Exception as exc:
            ExceptionUtils.exception_traceback(exc)
            self._set_task(task_id, status="failed", message=str(exc))

    def restore_from_backup(self, filename: str) -> BackupRestoreResultDTO:
        if not filename:
            return BackupRestoreResultDTO(success=False, message="文件不存在")
        return restore_backup(filename)


def backup(full_backup: bool = False, bk_path: str | None = None) -> str | None:
    """创建 v2 备份；保留 full_backup 参数兼容旧调用."""
    del full_backup
    try:
        return create_backup(bk_path)
    except (ServiceError, RepositoryError, DomainError):
        raise
    except Exception as exc:
        log.error(f"[Backup]创建备份失败: {exc}")
        ExceptionUtils.exception_traceback(exc)
        return None
