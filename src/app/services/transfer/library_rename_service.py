"""媒体库批量重命名服务编排."""

from __future__ import annotations

import time
import uuid
from typing import Any

import log
from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.db.repositories.category_repo_adapter import CategoryConfigRepositoryAdapter
from app.db.repositories.library_rename_repo_adapter import LibraryRenameRepositoryAdapter
from app.db.repositories.library_rename_repository import now_str
from app.domain.mediatypes import MediaType
from app.infrastructure.distributed_lock.lock_manager import get_lock_manager
from app.services.transfer.library_rename_backend import (
    basename,
    dirname,
    norm_path,
    normalize_backend,
    resolve_backend,
)
from app.services.transfer.library_rename_executor import LibraryRenameExecutor
from app.services.transfer.library_rename_metadata import LibraryMetadataResolver
from app.services.transfer.library_rename_models import RenameScope
from app.services.transfer.library_rename_planner import LibraryRenamePlanner
from app.utils import PathUtils
from app.utils.json_utils import JsonUtils

_PLAN_TTL_SECONDS = 24 * 3600
_MAX_LIMIT = 20000


class LibraryRenameService:
    """媒体库批量重命名业务服务."""

    def __init__(
        self,
        rename_repo: LibraryRenameRepositoryAdapter,
        storage_repo,
        media_config_service,
        media_service,
        media_server,
        download_repo,
        thread_executor,
        transfer_history_service=None,
        metadata_service=None,
    ):
        self._repo = rename_repo
        self._storage_repo = storage_repo
        self._media_config_service = media_config_service
        self._media_service = media_service
        self._media_server = media_server
        self._download_repo = download_repo
        self._thread_executor = thread_executor
        self._transfer_history_service = transfer_history_service
        self._metadata_service = metadata_service
        self._category_repo = CategoryConfigRepositoryAdapter()
        self._executor = LibraryRenameExecutor(
            rename_repo,
            storage_repo,
            media_server=media_server,
            on_finished=self._invalidate_history_cache,
        )

    # ---------- plan ----------

    def create_plan(self, scope_data: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        scope = self._parse_scope(scope_data)
        resolver = LibraryMetadataResolver(self._media_service, self._media_server, self._repo, self._download_repo)
        planner = LibraryRenamePlanner(
            self._media_config_service,
            self._storage_repo,
            resolver,
            self._media_service,
            self._category_repo,
            metadata_service=self._metadata_service,
        )
        rule_snapshot = planner.prepare(scope)
        items = planner.build_items(scope)
        plan_id = uuid.uuid4().hex
        job_id = self._repo.create_job(plan_id, scope.to_dict(), rule_snapshot, user_id)
        self._repo.add_items(job_id, items)
        self._repo.refresh_job_counters(job_id)
        job = self._repo.get_job(job_id) or {}
        log.info(f"[LibraryRename]计划 {plan_id} 生成完成: {len(items)} 项")
        return self._job_view(job)

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        job = self._repo.get_job_by_plan(plan_id)
        if not job:
            raise ResourceNotFoundError(f"未找到重命名计划: {plan_id}")
        return self._job_view(job)

    def list_items(
        self, plan_id: str, page: int = 1, page_size: int = 100, action: str | None = None
    ) -> dict[str, Any]:
        job = self._repo.get_job_by_plan(plan_id)
        if not job:
            raise ResourceNotFoundError(f"未找到重命名计划: {plan_id}")
        total, rows = self._repo.list_items(int(job["ID"]), page, page_size, action)
        return {
            "plan_id": plan_id,
            "total": total,
            "page": max(1, int(page)),
            "page_size": max(1, int(page_size)),
            "items": [self._item_view(row) for row in rows],
        }

    # ---------- execute ----------

    def execute(self, plan_id: str) -> dict[str, Any]:
        job = self._repo.get_job_by_plan(plan_id)
        if not job:
            raise ResourceNotFoundError(f"未找到重命名计划: {plan_id}")
        if job.get("STATUS") != "planned":
            raise ValidationError(f"计划状态不可执行: {job.get('STATUS')}")
        if _is_expired(job.get("CREATED_AT")):
            raise ValidationError("计划已过期，请重新预览")
        self._thread_executor.submit(self._executor.run_job, int(job["ID"]))
        return self._job_view(job)

    def get_job(self, job_id: int) -> dict[str, Any]:
        job = self._repo.get_job(job_id)
        if not job:
            raise ResourceNotFoundError(f"未找到重命名任务: {job_id}")
        return self._job_view(job)

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        if not self._executor.cancel_job(job_id):
            raise ValidationError("当前任务状态不可取消")
        return self.get_job(job_id)

    def rollback_job(self, job_id: int) -> dict[str, Any]:
        result = self._executor.rollback_job(job_id)
        if not result.get("ok"):
            raise ValidationError(f"回滚失败: {result.get('reason')}")
        return {**self.get_job(job_id), **result}

    def _invalidate_history_cache(self) -> None:
        if self._transfer_history_service is not None:
            self._transfer_history_service.invalidate_cache()

    # ---------- restart recovery ----------

    def recover_interrupted_jobs(self) -> int:
        """启动时把 running 任务标记为 interrupted，并按路径实际存在性修正条目."""
        recovered = 0
        for job in self._repo.list_running_jobs():
            job_id = int(job["ID"])
            lock = get_lock_manager().create_lock(f"library:rename:job:{job_id}", ttl_seconds=60)
            if not lock.acquire():
                log.info(f"[LibraryRename]任务 {job_id} 仍在其他实例执行，跳过恢复")
                continue
            try:
                self._recover_job(job_id)
                recovered += 1
            finally:
                lock.release()
        return recovered

    def _recover_job(self, job_id: int) -> None:
        for item in self._repo.list_running_items(job_id):
            old_path = norm_path(item.get("OLD_PATH") or "")
            new_path = norm_path(item.get("NEW_PATH") or "")
            backend = resolve_backend(self._storage_repo, item.get("BACKEND_ID"))
            if backend is None or not new_path:
                self._repo.update_item(int(item["ID"]), STATUS="manual_intervention", ERROR="interrupted")
                continue
            old_exists = backend.exists(old_path)
            new_exists = backend.exists(new_path)
            if new_exists and not old_exists:
                self._repo.update_history_dest(
                    dirname(old_path),
                    basename(old_path),
                    dirname(new_path),
                    basename(new_path),
                    category=self._executor._history_category(item, target=True),
                )
                self._repo.update_metadata_path(normalize_backend(item.get("BACKEND_ID")), old_path, new_path)
                self._executor._upsert_metadata(item, backend, new_path)
                self._repo.update_item(int(item["ID"]), STATUS="done", ROLLBACK_STATUS="recoverable")
            elif old_exists and not new_exists:
                self._repo.update_item(int(item["ID"]), STATUS="failed", ERROR="interrupted")
            else:
                self._repo.update_item(int(item["ID"]), STATUS="manual_intervention", ERROR="interrupted")
        self._repo.update_job_status(job_id, "interrupted", FINISHED_AT=now_str())
        self._repo.refresh_job_counters(job_id)

    # ---------- manual metadata ----------

    def set_manual_metadata(
        self,
        backend_id: str,
        path: str,
        media_type: str,
        title: str | None,
        year: str | None,
        tmdbid: str | int | None,
        season: int | str | None,
        episode: int | str | None,
        metadata_ref: str | None = None,
        anchor_provider: str | None = None,
        anchor_external_id: str | None = None,
        content_profile: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_path = norm_path(path)
        self._validate_library_path(backend_id, normalized_path)
        mtype = MediaType.from_string(media_type)
        if mtype == MediaType.UNKNOWN:
            raise ValidationError(f"非法媒体类型: {media_type}")
        if mtype != MediaType.MOVIE and (season is None or episode is None):
            raise ValidationError("剧集必须提供 season 和 episode")
        ref_provider = str(anchor_provider or "").strip()
        ref_external = str(anchor_external_id or "").strip()
        if not ref_provider and metadata_ref and ":" in metadata_ref:
            ref_provider, ref_external = metadata_ref.split(":", 1)
        if not ref_provider and str(tmdbid or "").isdigit():
            ref_provider, ref_external = "tmdb", str(tmdbid)
        is_tmdb = ref_provider == "tmdb"
        self._repo.upsert_metadata(
            normalize_backend(backend_id),
            normalized_path,
            {
                "type": mtype.value,
                "title": title or "",
                "year": year or "",
                "tmdbid": ref_external if is_tmdb else "",
                "identity_id": None,
                "anchor_provider": ref_provider or None,
                "anchor_external_id": ref_external or None,
                "content_profile": content_profile or "default",
                "metadata_ref": f"{ref_provider}:{ref_external}" if ref_provider and ref_external else None,
                "metadata_policy": "tmdb_primary" if is_tmdb else "provider_primary",
                "season": season if season is not None else "",
                "episode": episode if episode is not None else "",
                "metadata_source": "manual",
                "confidence": "high",
                "is_manual": True,
            },
            is_manual=True,
            user_id=user_id,
        )
        return {"backend_id": normalize_backend(backend_id), "path": normalized_path}

    # ---------- helpers ----------

    def _parse_scope(self, data: dict[str, Any]) -> RenameScope:
        raw_types = data.get("media_types") or ["movie", "tv", "anime"]
        types: list[MediaType] = []
        for value in raw_types:
            media_type = MediaType.from_string(str(value))
            if media_type != MediaType.UNKNOWN and media_type not in types:
                types.append(media_type)
        if not types:
            raise ValidationError("media_types 不能为空")
        layout = str(data.get("layout_mode") or "full")
        if layout not in ("full", "filename_only"):
            raise ValidationError(f"非法 layout_mode: {layout}")
        try:
            limit = int(data.get("limit") or 5000)
        except (TypeError, ValueError):
            raise ValidationError("limit 必须是整数") from None
        return RenameScope(
            media_types=types,
            roots=[norm_path(item) for item in (data.get("roots") or []) if item],
            layout_mode=layout,
            preserve_current_category=bool(data.get("preserve_current_category", True)),
            reorganize_category=bool(data.get("reorganize_category", False)),
            use_mediaserver_metadata=bool(data.get("use_mediaserver_metadata", True)),
            allow_online_metadata=bool(data.get("allow_online_metadata", False)),
            reidentify_no_metadata=bool(data.get("reidentify_no_metadata", False)),
            limit=max(1, min(limit, _MAX_LIMIT)),
            server_id=int(data["server_id"]) if data.get("server_id") else None,
        )

    def _validate_library_path(self, backend_id: str, path: str) -> None:
        cfg = self._media_config_service.get_config()
        normalized_backend = normalize_backend(backend_id)
        for suffix in ("movie", "tv", "anime"):
            paths = cfg.get(f"{suffix}_path") or []
            backends = cfg.get(f"{suffix}_backend") or []
            for index, root in enumerate(paths):
                root_backend = str(backends[index]) if index < len(backends) and backends[index] else "local"
                if normalize_backend(root_backend) != normalized_backend:
                    continue
                if PathUtils.is_path_in_path(root, path):
                    return
        raise ValidationError(f"路径不在媒体库范围内: {path}")

    def _job_view(self, job: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": int(job["ID"]),
            "plan_id": job.get("PLAN_ID"),
            "status": job.get("STATUS"),
            "scope": _load_json(job.get("SCOPE")),
            "total": int(job.get("TOTAL") or 0),
            "changed": int(job.get("CHANGED") or 0),
            "unchanged": int(job.get("UNCHANGED") or 0),
            "skipped": int(job.get("SKIPPED") or 0),
            "conflict": int(job.get("CONFLICT") or 0),
            "needs_metadata": int(job.get("NEEDS_METADATA") or 0),
            "failed": int(job.get("FAILED") or 0),
            "done": int(job.get("DONE") or 0),
            "rolled_back": int(job.get("ROLLED_BACK") or 0),
            "created_by": job.get("CREATED_BY"),
            "created_at": job.get("CREATED_AT"),
            "started_at": job.get("STARTED_AT"),
            "finished_at": job.get("FINISHED_AT"),
        }

    @staticmethod
    def _item_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(item["ID"]),
            "backend_id": item.get("BACKEND_ID"),
            "root": item.get("ROOT"),
            "old_path": item.get("OLD_PATH"),
            "new_path": item.get("NEW_PATH"),
            "action": item.get("ACTION"),
            "status": item.get("STATUS"),
            "reason": item.get("REASON"),
            "error": item.get("ERROR"),
            "metadata_source": item.get("METADATA_SOURCE"),
            "metadata": _load_json(item.get("METADATA_SNAPSHOT")),
        }


def _load_json(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        loaded = JsonUtils.loads(value)
        return loaded if isinstance(loaded, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _is_expired(created_at: str | None) -> bool:
    if not created_at:
        return True
    try:
        created = time.mktime(time.strptime(created_at, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return True
    return (time.time() - created) > _PLAN_TTL_SECONDS
