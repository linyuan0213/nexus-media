"""媒体库批量重命名仓储."""

import hashlib
import time
from typing import Any, cast

from app.db.models import (
    LIBRARYMEDIAMETADATA,
    LIBRARYRENAMEITEM,
    LIBRARYRENAMEJOB,
    TRANSFERHISTORY,
)
from app.db.repositories.base_repository import BaseRepository
from app.media.metadata.policy import ANCHOR_POLICY
from app.services.identity_resolver import IdentityResolver
from app.utils.json_utils import JsonUtils


def path_hash(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


class LibraryRenameRepository(BaseRepository):
    """批量重命名 job/item 与库内元数据缓存."""

    # ---------- job ----------

    def create_job(self, plan_id: str, scope: dict, rule_snapshot: dict, created_by: int | None = None) -> int:
        with self.session() as db:
            job = LIBRARYRENAMEJOB(
                PLAN_ID=plan_id,
                STATUS="planned",
                SCOPE=JsonUtils.dumps(scope, ensure_ascii=False),
                RULE_SNAPSHOT=JsonUtils.dumps(rule_snapshot, ensure_ascii=False),
                CREATED_BY=created_by,
                CREATED_AT=now_str(),
            )
            db.add(job)
            db.flush()
            return int(job.ID)

    def get_job(self, job_id: int) -> LIBRARYRENAMEJOB | None:
        with self.session() as db:
            return db.query(LIBRARYRENAMEJOB).filter(LIBRARYRENAMEJOB.ID == int(job_id)).first()

    def get_job_by_plan(self, plan_id: str) -> LIBRARYRENAMEJOB | None:
        if not plan_id:
            return None
        with self.session() as db:
            return db.query(LIBRARYRENAMEJOB).filter(LIBRARYRENAMEJOB.PLAN_ID == plan_id).first()

    def update_job(self, job_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        with self.session() as db:
            db.query(LIBRARYRENAMEJOB).filter(LIBRARYRENAMEJOB.ID == int(job_id)).update(cast(Any, kwargs))

    def update_job_status(self, job_id: int, status: str, **kwargs: Any) -> None:
        values = {"STATUS": status, **kwargs}
        self.update_job(job_id, **values)

    def list_running_jobs(self) -> list[LIBRARYRENAMEJOB]:
        with self.session() as db:
            return (
                db.query(LIBRARYRENAMEJOB)
                .filter(LIBRARYRENAMEJOB.STATUS == "running")
                .order_by(LIBRARYRENAMEJOB.ID.asc())
                .all()
            )

    def refresh_job_counters(self, job_id: int) -> None:
        with self.session() as db:
            rows = (
                db.query(LIBRARYRENAMEITEM.ACTION, LIBRARYRENAMEITEM.STATUS)
                .filter(LIBRARYRENAMEITEM.JOB_ID == int(job_id))
                .all()
            )
            total = len(rows)
            changed = sum(1 for action, _ in rows if action == "rename")
            unchanged = sum(1 for action, _ in rows if action == "unchanged")
            skipped = sum(1 for action, _ in rows if action == "skip")
            conflict = sum(1 for action, _ in rows if action == "conflict")
            needs_metadata = sum(1 for action, _ in rows if action == "needs_metadata")
            failed = sum(1 for _, status in rows if status in ("failed", "manual_intervention"))
            done = sum(1 for _, status in rows if status == "done")
            rolled_back = sum(1 for _, status in rows if status == "rolled_back")
            db.query(LIBRARYRENAMEJOB).filter(LIBRARYRENAMEJOB.ID == int(job_id)).update(
                {
                    "TOTAL": total,
                    "CHANGED": changed,
                    "UNCHANGED": unchanged,
                    "SKIPPED": skipped,
                    "CONFLICT": conflict,
                    "NEEDS_METADATA": needs_metadata,
                    "FAILED": failed,
                    "DONE": done,
                    "ROLLED_BACK": rolled_back,
                }
            )

    # ---------- item ----------

    def add_items(self, job_id: int, items: list[dict]) -> None:
        if not items:
            return
        with self.session() as db:
            for item in items:
                db.add(LIBRARYRENAMEITEM(JOB_ID=int(job_id), **item))

    def get_item(self, item_id: int) -> LIBRARYRENAMEITEM | None:
        with self.session() as db:
            return db.query(LIBRARYRENAMEITEM).filter(LIBRARYRENAMEITEM.ID == int(item_id)).first()

    def list_items(
        self, job_id: int, page: int = 1, page_size: int = 100, action: str | None = None
    ) -> tuple[int, list[LIBRARYRENAMEITEM]]:
        with self.session() as db:
            query = db.query(LIBRARYRENAMEITEM).filter(LIBRARYRENAMEITEM.JOB_ID == int(job_id))
            if action:
                query = query.filter(LIBRARYRENAMEITEM.ACTION == action)
            total = query.count()
            rows = (
                query.order_by(LIBRARYRENAMEITEM.ID.asc())
                .limit(max(1, int(page_size)))
                .offset(max(0, (max(1, int(page)) - 1) * max(1, int(page_size))))
                .all()
            )
            return total, rows

    def list_running_items(self, job_id: int) -> list[LIBRARYRENAMEITEM]:
        with self.session() as db:
            return (
                db.query(LIBRARYRENAMEITEM)
                .filter(
                    LIBRARYRENAMEITEM.JOB_ID == int(job_id),
                    LIBRARYRENAMEITEM.STATUS == "running",
                )
                .order_by(LIBRARYRENAMEITEM.ID.asc())
                .all()
            )

    def list_all_items(self, job_id: int) -> list[LIBRARYRENAMEITEM]:
        with self.session() as db:
            return (
                db.query(LIBRARYRENAMEITEM)
                .filter(LIBRARYRENAMEITEM.JOB_ID == int(job_id))
                .order_by(LIBRARYRENAMEITEM.ID.asc())
                .all()
            )

    def list_planned_items(self, job_id: int) -> list[LIBRARYRENAMEITEM]:
        with self.session() as db:
            return (
                db.query(LIBRARYRENAMEITEM)
                .filter(
                    LIBRARYRENAMEITEM.JOB_ID == int(job_id),
                    LIBRARYRENAMEITEM.STATUS == "planned",
                    LIBRARYRENAMEITEM.ACTION == "rename",
                )
                .order_by(LIBRARYRENAMEITEM.ID.asc())
                .all()
            )

    def update_item(self, item_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        with self.session() as db:
            db.query(LIBRARYRENAMEITEM).filter(LIBRARYRENAMEITEM.ID == int(item_id)).update(cast(Any, kwargs))

    def list_done_items(self, job_id: int) -> list[LIBRARYRENAMEITEM]:
        with self.session() as db:
            return (
                db.query(LIBRARYRENAMEITEM)
                .filter(
                    LIBRARYRENAMEITEM.JOB_ID == int(job_id),
                    LIBRARYRENAMEITEM.STATUS.in_(("done", "failed")),
                )
                .order_by(LIBRARYRENAMEITEM.ID.desc())
                .all()
            )

    def update_item_status_by_job(self, job_id: int, statuses: tuple[str, ...], **kwargs: Any) -> None:
        with self.session() as db:
            db.query(LIBRARYRENAMEITEM).filter(
                LIBRARYRENAMEITEM.JOB_ID == int(job_id),
                LIBRARYRENAMEITEM.STATUS.in_(statuses),
            ).update(cast(Any, kwargs))

    # ---------- history ----------

    def get_history_by_dest(self, dest_path: str, dest_filename: str) -> list[TRANSFERHISTORY]:
        with self.session() as db:
            return (
                db.query(TRANSFERHISTORY)
                .filter(
                    TRANSFERHISTORY.DEST_PATH == dest_path,
                    TRANSFERHISTORY.DEST_FILENAME == dest_filename,
                )
                .order_by(TRANSFERHISTORY.DATE.desc(), TRANSFERHISTORY.ID.desc())
                .all()
            )

    def update_history_dest_by_path(
        self,
        old_path: str,
        old_filename: str,
        new_path: str,
        new_filename: str,
        category: str | None = None,
    ) -> int:
        with self.session() as db:
            values: dict[str, Any] = {"DEST_PATH": new_path, "DEST_FILENAME": new_filename}
            if category is not None:
                values["CATEGORY"] = category
            return (
                db.query(TRANSFERHISTORY)
                .filter(
                    TRANSFERHISTORY.DEST_PATH == old_path,
                    TRANSFERHISTORY.DEST_FILENAME == old_filename,
                )
                .update(cast(Any, values))
            )

    # ---------- metadata cache ----------

    def get_metadata(self, backend_id: str, path: str) -> LIBRARYMEDIAMETADATA | None:
        with self.session() as db:
            return (
                db.query(LIBRARYMEDIAMETADATA)
                .filter(
                    LIBRARYMEDIAMETADATA.BACKEND_ID == str(backend_id or "local"),
                    LIBRARYMEDIAMETADATA.PATH_HASH == path_hash(path),
                )
                .first()
            )

    def upsert_metadata(
        self,
        backend_id: str,
        path: str,
        data: dict[str, Any],
        *,
        is_manual: bool = False,
        user_id: int | None = None,
    ) -> None:
        now = now_str()
        resolved = IdentityResolver().resolve_values(
            identity_id=data.get("identity_id"),
            provider=data.get("anchor_provider"),
            external_id=data.get("anchor_external_id"),
            title=data.get("title"),
            year=data.get("year"),
            media_type=data.get("type") or "movie",
            content_profile=data.get("content_profile"),
            allow_local=False,
        )
        values = {
            "BACKEND_ID": str(backend_id or "local"),
            "PATH": path,
            "PATH_HASH": path_hash(path),
            "TYPE": str(data.get("type") or ""),
            "TITLE": str(data.get("title") or ""),
            "YEAR": str(data.get("year") or ""),
            "TMDBID": str(data.get("tmdbid") or ""),
            "IDENTITY_ID": resolved.identity_id or None,
            "ANCHOR_PROVIDER": data.get("anchor_provider"),
            "ANCHOR_EXTERNAL_ID": data.get("anchor_external_id"),
            "CONTENT_PROFILE": data.get("content_profile") or "default",
            "METADATA_POLICY": data.get("metadata_policy") or ANCHOR_POLICY.get(str(data.get("anchor_provider") or "")),
            "NAMING_PROFILE": data.get("naming_profile"),
            "SEASON": str(data.get("season") or ""),
            "EPISODE": str(data.get("episode") or ""),
            "SEASON_EPISODE_COUNT": data.get("season_episode_count"),
            "SOURCE_FILENAME": data.get("source_filename"),
            "METADATA_SOURCE": str(data.get("metadata_source") or ""),
            "CONFIDENCE": str(data.get("confidence") or "medium"),
            "IS_MANUAL": 1 if is_manual else int(data.get("is_manual") or 0),
            "FILE_SIZE": data.get("file_size"),
            "FILE_MTIME": data.get("file_mtime"),
            "RAW": JsonUtils.dumps(data.get("raw") or {}, ensure_ascii=False),
            "UPDATED_AT": now,
            "UPDATED_BY": user_id,
        }
        with self.session() as db:
            row = (
                db.query(LIBRARYMEDIAMETADATA)
                .filter(
                    LIBRARYMEDIAMETADATA.BACKEND_ID == values["BACKEND_ID"],
                    LIBRARYMEDIAMETADATA.PATH_HASH == values["PATH_HASH"],
                )
                .first()
            )
            if row:
                if row.IS_MANUAL and not is_manual:
                    return
                if not is_manual and row.CONFIDENCE == "high" and values["CONFIDENCE"] != "high":
                    return
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                db.add(LIBRARYMEDIAMETADATA(CREATED_AT=now, **values))

    def update_metadata_path(
        self,
        backend_id: str,
        old_path: str,
        new_path: str,
        *,
        file_size: int | None = None,
        file_mtime: float | None = None,
    ) -> None:
        with self.session() as db:
            row = (
                db.query(LIBRARYMEDIAMETADATA)
                .filter(
                    LIBRARYMEDIAMETADATA.BACKEND_ID == str(backend_id or "local"),
                    LIBRARYMEDIAMETADATA.PATH_HASH == path_hash(old_path),
                )
                .first()
            )
            if not row:
                return
            row.PATH = new_path
            row.PATH_HASH = path_hash(new_path)
            row.FILE_SIZE = file_size
            row.FILE_MTIME = file_mtime
            row.UPDATED_AT = now_str()
