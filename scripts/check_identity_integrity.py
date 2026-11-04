"""生产身份完整性审计；发现影子身份/空身份/同作品多身份时返回非 0."""

from __future__ import annotations

import json
import sys

from sqlalchemy import func, inspect

from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle
from app.db.models.subscribe import SubscribeMovies, SubscribeTvs
from app.db.repositories.base_repository import BaseRepository


def _count(db, model) -> int:
    return int(db.query(func.count()).select_from(model).scalar() or 0)


def _null_identity(db, model) -> int:
    return int(
        db.query(func.count())
        .select_from(model)
        .filter((model.IDENTITY_ID.is_(None)) | (model.IDENTITY_ID == ""))
        .scalar()
        or 0
    )


def audit() -> dict:
    with BaseRepository().readonly() as db:
        tables = set(inspect(db.get_bind()).get_table_names())
        result: dict = {"tables": {}}
        allowed_empty = {"SEARCH_RESULT_INFO", "MEDIASYNC_ITEMS"}
        for label, model in (
            ("SEARCH_RESULT_INFO", SEARCHRESULTINFO),
            ("DOWNLOAD_HISTORY", DOWNLOADHISTORY),
            ("TRANSFER_HISTORY", TRANSFERHISTORY),
            ("MEDIA_LIFECYCLE", MediaLifecycle),
            ("SUBSCRIBE_MOVIES", SubscribeMovies),
            ("SUBSCRIBE_TVS", SubscribeTvs),
        ):
            if model.__tablename__ not in tables:
                continue
            result["tables"][label] = {
                "total": _count(db, model),
                "empty_identity": _null_identity(db, model),
                "allowed_empty": label in allowed_empty,
            }

        shadow = 0
        duplicate_groups = 0
        if MediaLifecycle.__tablename__ in tables:
            shadow = int(
                db.query(func.count(func.distinct(MediaLifecycle.IDENTITY_ID)))
                .filter(
                    (MediaLifecycle.IDENTITY_ID.like("local:%"))
                    | (MediaLifecycle.IDENTITY_ID.like("content_id:%"))
                )
                .scalar()
                or 0
            )
            duplicate_groups = int(
                db.query(func.count())
                .select_from(
                    db.query(
                        MediaLifecycle.TITLE,
                        MediaLifecycle.YEAR,
                        MediaLifecycle.MEDIA_TYPE,
                    )
                    .group_by(MediaLifecycle.TITLE, MediaLifecycle.YEAR, MediaLifecycle.MEDIA_TYPE)
                    .having(func.count(func.distinct(MediaLifecycle.IDENTITY_ID)) > 1)
                    .subquery()
                )
                .scalar()
                or 0
            )
    result["lifecycle_shadow_identities"] = shadow
    result["duplicate_title_identity_groups"] = duplicate_groups
    failures = []
    if shadow:
        failures.append("shadow_identities")
    if duplicate_groups:
        failures.append("duplicate_title_identity_groups")
    for label, data in result["tables"].items():
        if data["empty_identity"] and not data["allowed_empty"]:
            failures.append(f"empty_identity:{label}")
    result["failures"] = failures
    return result


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(1 if report["failures"] else 0)
