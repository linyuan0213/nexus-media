"""把生命周期快照 LAST_EVENT_AT 回退到当前阶段最近的真实事件，隐藏被忽略的新循环事件."""

from __future__ import annotations

from sqlalchemy import func

from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.repositories.base_repository import BaseRepository


def repair() -> dict[str, int]:
    counts = {"scanned": 0, "repaired": 0}
    with BaseRepository().session() as db:
        snapshots = db.query(MediaLifecycle).all()
        for snapshot in snapshots:
            counts["scanned"] += 1
            latest = (
                db.query(func.max(MediaLifecycleEvent.OCCURRED_AT))
                .filter(
                    MediaLifecycleEvent.IDENTITY_ID == snapshot.IDENTITY_ID,
                    MediaLifecycleEvent.SEASON == snapshot.SEASON,
                    MediaLifecycleEvent.EPISODE == snapshot.EPISODE,
                    MediaLifecycleEvent.STAGE == snapshot.STAGE,
                    MediaLifecycleEvent.STATUS == snapshot.STATUS,
                )
                .scalar()
            )
            if latest is not None and latest != snapshot.LAST_EVENT_AT:
                snapshot.LAST_EVENT_AT = latest
                counts["repaired"] += 1
        db.commit()
    return counts


if __name__ == "__main__":
    print(repair())
