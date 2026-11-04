"""把误落库的 /img/blur 海报还原为原始 URL，避免关闭 SFW 后仍模糊."""

from __future__ import annotations

from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle
from app.db.repositories.base_repository import BaseRepository
from app.media.display_image_policy import unwrap_display_image_url


def repair() -> dict[str, int]:
    counts: dict[str, int] = {}
    with BaseRepository().session() as db:
        for model in (MediaLifecycle, DOWNLOADHISTORY, TRANSFERHISTORY, SEARCHRESULTINFO):
            column = getattr(model, "POSTER", None)
            if column is None:
                continue
            rows = db.query(model).filter(column.like("/img/blur%")).all()
            for row in rows:
                setattr(row, "POSTER", unwrap_display_image_url(getattr(row, "POSTER")))
            counts[model.__tablename__] = len(rows)
        db.commit()
    return counts


if __name__ == "__main__":
    print(repair())
