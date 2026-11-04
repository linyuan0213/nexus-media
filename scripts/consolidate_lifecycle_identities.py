"""按媒体标题归并重复生命周期身份.

用于清理历史 backfill/local/content_id 影子身份造成的同作品多身份问题。
默认仅预览，加 --apply 执行。
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import datetime

from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.models.media_identity import MediaExternalRef, MediaIdentity
from app.db.models.subscribe import SubscribeHistory, SubscribeMovies, SubscribeTvEpisodes, SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.domain.lifecycle import stage_rank


def _normalize_title(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


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
            db.query(MediaLifecycle).filter(MediaLifecycle.ID == row.ID).update(
                {"IDENTITY_ID": target_id}, synchronize_session=False
            )
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
        db.query(MediaLifecycle).filter(MediaLifecycle.ID == row.ID).delete(synchronize_session=False)
        deleted += 1
    return moved, deleted


def _move(db, source_id: str, target_id: str) -> dict[str, int]:
    counts = {"histories": 0, "search": 0, "events": 0, "snapshots": 0}
    for model in (
        DOWNLOADHISTORY,
        TRANSFERHISTORY,
        SubscribeMovies,
        SubscribeTvs,
        SubscribeTvEpisodes,
        SubscribeHistory,
    ):
        counts["histories"] += (
            db.query(model)
            .filter(model.IDENTITY_ID == source_id)
            .update({"IDENTITY_ID": target_id}, synchronize_session=False)
        )
    counts["search"] += (
        db.query(SEARCHRESULTINFO)
        .filter(SEARCHRESULTINFO.IDENTITY_ID == source_id)
        .update({"IDENTITY_ID": target_id}, synchronize_session=False)
    )
    counts["events"] += (
        db.query(MediaLifecycleEvent)
        .filter(MediaLifecycleEvent.IDENTITY_ID == source_id)
        .update({"IDENTITY_ID": target_id}, synchronize_session=False)
    )
    for ref in db.query(MediaExternalRef).filter(MediaExternalRef.IDENTITY_ID == source_id).all():
        exists = (
            db.query(MediaExternalRef.ID)
            .filter(
                MediaExternalRef.IDENTITY_ID == target_id,
                MediaExternalRef.PROVIDER == ref.PROVIDER,
                MediaExternalRef.EXTERNAL_ID == ref.EXTERNAL_ID,
                MediaExternalRef.SCOPE == ref.SCOPE,
            )
            .first()
        )
        if exists is not None:
            db.query(MediaExternalRef).filter(MediaExternalRef.ID == ref.ID).delete(synchronize_session=False)
        else:
            db.query(MediaExternalRef).filter(MediaExternalRef.ID == ref.ID).update(
                {"IDENTITY_ID": target_id}, synchronize_session=False
            )
    moved, deleted = _merge_snapshots(db, source_id, target_id)
    counts["snapshots"] += moved + deleted
    db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == source_id).delete(synchronize_session=False)
    db.expire_all()
    return counts


_CODE_RE = re.compile(r"^[A-Za-z]{2,12}[-_ ]?\d{2,6}$")


def _normalize_code(value: str) -> str:
    return re.sub(r"[-_ ]", "", str(value or "")).upper()


def _merge_code_groups(db, apply: bool, counts: dict[str, int]) -> None:
    refs = db.query(MediaExternalRef.EXTERNAL_ID, MediaExternalRef.IDENTITY_ID).all()
    groups: dict[str, set[str]] = defaultdict(set)
    for external_id, identity_id in refs:
        if external_id and _CODE_RE.match(str(external_id)):
            groups[_normalize_code(external_id)].add(str(identity_id))
    for code, identity_ids in sorted(groups.items()):
        if len(identity_ids) < 2:
            continue
        scored = []
        for identity_id in identity_ids:
            rows = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == identity_id).count()
            ref_count = db.query(MediaExternalRef).filter(MediaExternalRef.IDENTITY_ID == identity_id).count()
            identity = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == identity_id).first()
            scored.append((rows, ref_count, 1 if identity is not None else 0, identity_id))
        scored.sort(reverse=True)
        target_id = scored[0][3]
        counts["code_groups"] += 1
        if not apply:
            print("would merge code", code, "->", target_id, "from", [item[3] for item in scored[1:]])
            continue
        for _, _, _, source_id in scored[1:]:
            result = _move(db, source_id, target_id)
            for name, value in result.items():
                counts[name] = counts.get(name, 0) + value
            counts["merged"] += 1


def consolidate(apply: bool) -> dict[str, int]:
    counts = {"groups": 0, "code_groups": 0, "merged": 0, "identities_before": 0, "identities_after": 0}
    with BaseRepository().session() as db:
        rows = (
            db.query(
                MediaLifecycle.IDENTITY_ID,
                MediaLifecycle.TITLE,
                MediaLifecycle.YEAR,
                MediaLifecycle.MEDIA_TYPE,
            )
            .distinct()
            .all()
        )
        groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for identity_id, title, year, media_type in rows:
            key = (_normalize_title(title), str(year or ""), str(media_type or ""))
            if key[0]:
                groups[key].append(str(identity_id))
        counts["identities_before"] = len({str(row[0]) for row in rows})

        for key, identity_ids in groups.items():
            unique_ids = sorted(set(identity_ids))
            if len(unique_ids) < 2:
                continue
            scored = []
            for identity_id in unique_ids:
                row_count = db.query(MediaLifecycle).filter(MediaLifecycle.IDENTITY_ID == identity_id).count()
                identity = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == identity_id).first()
                scored.append((row_count, 1 if identity is not None else 0, identity_id))
            scored.sort(reverse=True)
            target_id = scored[0][2]
            counts["groups"] += 1
            if not apply:
                print("would merge", key, "->", target_id, "from", [item[2] for item in scored[1:]])
                continue
            for _, _, source_id in scored[1:]:
                result = _move(db, source_id, target_id)
                for name, value in result.items():
                    counts[name] = counts.get(name, 0) + value
                counts["merged"] += 1
        _merge_code_groups(db, apply, counts)
        if apply:
            db.commit()
            counts["identities_after"] = (
                db.query(MediaLifecycle.IDENTITY_ID).distinct().count()
            )
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(consolidate(args.apply))
