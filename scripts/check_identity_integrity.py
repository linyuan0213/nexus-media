"""生产身份完整性审计；发现影子身份/空身份/同作品多身份时返回非 0."""

from __future__ import annotations

import json
import sys

from sqlalchemy import func, inspect

from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle
from app.db.models.media_identity import MediaExternalRef, MediaIdentity
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
                    (MediaLifecycle.IDENTITY_ID.like("local:%")) | (MediaLifecycle.IDENTITY_ID.like("content_id:%"))
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
    subscription_orphans = 0
    missing_ref_identities = 0
    lifecycle_unknown = 0
    if SubscribeMovies.__tablename__ in tables and MediaIdentity.__tablename__ in tables:
        for model in (SubscribeMovies, SubscribeTvs):
            rows = db.query(model.IDENTITY_ID).all()
            for (identity_id,) in rows:
                if not identity_id or identity_id == "preview":
                    subscription_orphans += 1
                    continue
                exists = db.query(MediaIdentity.IDENTITY_ID).filter(MediaIdentity.IDENTITY_ID == identity_id).first()
                ref_exists = db.query(MediaExternalRef.ID).filter(MediaExternalRef.IDENTITY_ID == identity_id).first()
                if exists is None:
                    subscription_orphans += 1
                elif ref_exists is None:
                    missing_ref_identities += 1
    if MediaLifecycle.__tablename__ in tables and MediaIdentity.__tablename__ in tables:
        lifecycle_ids = {
            str(row[0])
            for row in db.query(MediaLifecycle.IDENTITY_ID)
            .filter(MediaLifecycle.IDENTITY_ID != "preview")
            .distinct()
            .all()
        }
        known_ids = {str(row[0]) for row in db.query(MediaIdentity.IDENTITY_ID).all()}
        lifecycle_unknown = len(lifecycle_ids - known_ids)
    result["lifecycle_shadow_identities"] = shadow
    result["duplicate_title_identity_groups"] = duplicate_groups
    result["subscription_orphan_identities"] = subscription_orphans
    result["subscription_missing_ref_identities"] = missing_ref_identities
    result["lifecycle_unknown_identities"] = lifecycle_unknown
    failures = []
    if shadow:
        failures.append("shadow_identities")
    if duplicate_groups:
        failures.append("duplicate_title_identity_groups")
    if subscription_orphans:
        failures.append("subscription_orphan_identities")
    if missing_ref_identities:
        failures.append("subscription_missing_ref_identities")
    if lifecycle_unknown:
        failures.append("lifecycle_unknown_identities")
    for label, data in result["tables"].items():
        if data["empty_identity"] and not data["allowed_empty"]:
            failures.append(f"empty_identity:{label}")
    result["failures"] = failures
    return result


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(1 if report["failures"] else 0)
