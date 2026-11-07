"""合并共享同一外部引用（provider+external_id+scope）的重复身份."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.models.media_identity import MediaExternalRef, MediaIdentity
from app.db.repositories.base_repository import BaseRepository
from app.domain.lifecycle import stage_rank


def _merge_snapshots(db, source_id: str, target_id: str) -> tuple[int, int]:
    moved = 0
    deleted = 0
    for row in db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == source_id).all():
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
            moved += 1
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
                "SOURCE_PROVIDER",
                "STAGE_STARTED_AT",
                "LAST_EVENT_AT",
                "LAST_ERROR",
            ):
                setattr(target, column, getattr(row, column))
        db.delete(row)
        deleted += 1
    return moved, deleted


def merge() -> dict[str, int]:
    counts = {"groups": 0, "identities": 0, "events": 0, "rows": 0, "refs": 0}
    with BaseRepository().session() as db:
        groups = (
            db.query(
                MediaExternalRef.PROVIDER,
                MediaExternalRef.EXTERNAL_ID,
            )
            .group_by(MediaExternalRef.PROVIDER, MediaExternalRef.EXTERNAL_ID)
            .having(func.count(func.distinct(MediaExternalRef.IDENTITY_ID)) > 1)
            .all()
        )
        for provider, external_id in groups:
            refs = (
                db.query(MediaExternalRef)
                .filter(
                    MediaExternalRef.PROVIDER == provider,
                    MediaExternalRef.EXTERNAL_ID == external_id,
                )
                .all()
            )
            identity_ids = list({ref.IDENTITY_ID for ref in refs})
            identities = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID.in_(identity_ids)).all()
            if len(identities) < 2:
                continue
            scored = []
            for identity in identities:
                rows = (
                    db.query(func.count(MediaLifecycle.ID))
                    .filter(MediaLifecycle.IDENTITY_ID == identity.IDENTITY_ID)
                    .scalar()
                )
                scored.append((int(rows or 0), identity.CREATED_AT or datetime.min, identity))
            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            target = scored[0][2]
            counts["groups"] += 1
            for _, _, source in scored[1:]:
                source_id = source.IDENTITY_ID
                target_id = target.IDENTITY_ID
                for source_ref in db.query(MediaExternalRef).filter(MediaExternalRef.IDENTITY_ID == source_id).all():
                    exists = (
                        db.query(MediaExternalRef.ID)
                        .filter(
                            MediaExternalRef.IDENTITY_ID == target_id,
                            MediaExternalRef.PROVIDER == source_ref.PROVIDER,
                            MediaExternalRef.EXTERNAL_ID == source_ref.EXTERNAL_ID,
                            MediaExternalRef.SCOPE == source_ref.SCOPE,
                        )
                        .first()
                    )
                    if exists is not None:
                        db.query(MediaExternalRef).filter(MediaExternalRef.ID == source_ref.ID).delete(
                            synchronize_session=False
                        )
                    else:
                        db.query(MediaExternalRef).filter(MediaExternalRef.ID == source_ref.ID).update(
                            {"IDENTITY_ID": target_id}, synchronize_session=False
                        )
                    counts["refs"] += 1
                db.expire_all()
                counts["events"] += (
                    db.query(MediaLifecycleEvent)
                    .filter(MediaLifecycleEvent.IDENTITY_ID == source_id)
                    .update({"IDENTITY_ID": target_id}, synchronize_session=False)
                )
                counts["rows"] += (
                    db.query(DOWNLOADHISTORY)
                    .filter(DOWNLOADHISTORY.IDENTITY_ID == source_id)
                    .update({"IDENTITY_ID": target_id}, synchronize_session=False)
                )
                counts["rows"] += (
                    db.query(TRANSFERHISTORY)
                    .filter(TRANSFERHISTORY.IDENTITY_ID == source_id)
                    .update({"IDENTITY_ID": target_id}, synchronize_session=False)
                )
                counts["rows"] += (
                    db.query(SEARCHRESULTINFO)
                    .filter(SEARCHRESULTINFO.IDENTITY_ID == source_id)
                    .update({"IDENTITY_ID": target_id}, synchronize_session=False)
                )
                moved, deleted = _merge_snapshots(db, source_id, target_id)
                counts["rows"] += moved + deleted
                db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == source_id).delete(synchronize_session=False)
                counts["identities"] += 1
        db.commit()
    return counts


if __name__ == "__main__":
    print(merge())
