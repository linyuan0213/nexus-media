"""把 local:* 影子身份归并到已有规范身份（按标题/年份/类型）。"""

from __future__ import annotations

from datetime import datetime

from app.db.models import DOWNLOADHISTORY, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.domain.lifecycle import stage_rank


def _media_type(value) -> str:
    key = str(value or "").lower()
    return {"mov": "movie", "movie": "movie", "tv": "tv", "ani": "anime", "anime": "anime"}.get(key, "movie")


def merge() -> dict[str, int]:
    repo = MediaIdentityRepository()
    counts = {"histories": 0, "events": 0, "snapshots": 0, "deleted": 0}
    with BaseRepository().session() as db:
        local_ids = {
            row[0]
            for row in db.query(MediaLifecycle.IDENTITY_ID)
            .filter(MediaLifecycle.IDENTITY_ID.like("local:%"))
            .distinct()
            .all()
        }
        local_ids |= {
            row[0]
            for row in db.query(DOWNLOADHISTORY.IDENTITY_ID)
            .filter(DOWNLOADHISTORY.IDENTITY_ID.like("local:%"))
            .distinct()
            .all()
        }
        local_ids |= {
            row[0]
            for row in db.query(TRANSFERHISTORY.IDENTITY_ID)
            .filter(TRANSFERHISTORY.IDENTITY_ID.like("local:%"))
            .distinct()
            .all()
        }
        for local_id in local_ids:
            source = (
                db.query(MediaLifecycle)
                .filter(MediaLifecycle.IDENTITY_ID == local_id)
                .order_by(MediaLifecycle.LAST_EVENT_AT.desc())
                .first()
            )
            if source is None:
                download = (
                    db.query(DOWNLOADHISTORY)
                    .filter(DOWNLOADHISTORY.IDENTITY_ID == local_id)
                    .order_by(DOWNLOADHISTORY.ID.desc())
                    .first()
                )
                if download is None:
                    transfer = (
                        db.query(TRANSFERHISTORY)
                        .filter(TRANSFERHISTORY.IDENTITY_ID == local_id)
                        .order_by(TRANSFERHISTORY.ID.desc())
                        .first()
                    )
                    if transfer is None:
                        continue
                    title, year, mediatype = transfer.TITLE, transfer.YEAR, transfer.TYPE
                else:
                    title, year, mediatype = download.TITLE, download.YEAR, download.TYPE
            else:
                title, year, mediatype = source.TITLE, source.YEAR, source.MEDIA_TYPE
            canonical = repo.find_by_title(title, year, _media_type(mediatype))
            if canonical is None or canonical.IDENTITY_ID == local_id:
                continue
            target_id = canonical.IDENTITY_ID
            counts["histories"] += (
                db.query(DOWNLOADHISTORY)
                .filter(DOWNLOADHISTORY.IDENTITY_ID == local_id)
                .update({"IDENTITY_ID": target_id}, synchronize_session=False)
            )
            counts["histories"] += (
                db.query(TRANSFERHISTORY)
                .filter(TRANSFERHISTORY.IDENTITY_ID == local_id)
                .update({"IDENTITY_ID": target_id}, synchronize_session=False)
            )
            counts["events"] += (
                db.query(MediaLifecycleEvent)
                .filter(MediaLifecycleEvent.IDENTITY_ID == local_id)
                .update({"IDENTITY_ID": target_id}, synchronize_session=False)
            )
            for row in db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == local_id).all():
                target = (
                    db.query(MediaLifecycle)
                    .filter(
                        MediaLifecycle.IDENTITY_ID == target_id,
                        MediaLifecycle.SEASON == row.SEASON,
                        MediaLifecycle.EPISODE == row.EPISODE,
                    )
                    .first()
                )
                if target is None:
                    row.IDENTITY_ID = target_id
                    counts["snapshots"] += 1
                    continue
                if stage_rank(row.STAGE) > stage_rank(target.STAGE) or (
                    stage_rank(row.STAGE) == stage_rank(target.STAGE)
                    and (row.LAST_EVENT_AT or row.STAGE_STARTED_AT or datetime.min)
                    > (target.LAST_EVENT_AT or target.STAGE_STARTED_AT or datetime.min)
                ):
                    for column in (
                        "STAGE",
                        "STATUS",
                        "PROGRESS",
                        "TITLE",
                        "YEAR",
                        "POSTER",
                        "STAGE_STARTED_AT",
                        "LAST_EVENT_AT",
                        "LAST_ERROR",
                    ):
                        setattr(target, column, getattr(row, column))
                db.delete(row)
                counts["deleted"] += 1
        db.commit()
    return counts


if __name__ == "__main__":
    print(merge())
