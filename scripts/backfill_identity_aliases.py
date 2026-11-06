"""从已有元数据快照回填 MEDIA_IDENTITY.ALIASES（默认 dry-run）.

只读本地快照，不访问 TMDB/豆瓣/Bangumi；用于让订阅关键词预筛直接复用历史别名。
"""

from __future__ import annotations

import argparse
import json

import log
from app.db.models.media_identity import MediaIdentity, MediaMetadataSnapshot
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.media.metadata.models import MediaMetadata


def _aliases_from_payload(payload: str) -> list[str]:
    try:
        metadata = MediaMetadata.model_validate_json(payload)
    except Exception:  # noqa: BLE001 - 旧快照不兼容时跳过
        return []
    values = list(metadata.aliases or [])
    for field_name in ("title", "original_title"):
        field = metadata.fields.get(field_name)
        value = getattr(field, "value", None)
        if value:
            values.append(str(value))
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    latest: dict[str, str] = {}
    with BaseRepository().session() as db:
        rows = (
            db.query(MediaMetadataSnapshot.IDENTITY_ID, MediaMetadataSnapshot.PAYLOAD)
            .order_by(MediaMetadataSnapshot.IDENTITY_ID, MediaMetadataSnapshot.ID.desc())
            .all()
        )
        identities = {
            row.IDENTITY_ID: row.CANONICAL_TITLE
            for row in db.query(MediaIdentity.IDENTITY_ID, MediaIdentity.CANONICAL_TITLE).all()
        }
    for identity_id, payload in rows:
        latest.setdefault(str(identity_id), payload)

    repo = MediaIdentityRepository()
    updated = skipped = 0
    for identity_id, payload in latest.items():
        aliases = _aliases_from_payload(payload)
        title = identities.get(identity_id)
        if title:
            aliases.append(str(title))
        aliases = [item for item in dict.fromkeys(aliases) if item]
        if not aliases:
            skipped += 1
            continue
        if args.apply:
            if repo.update_aliases(identity_id, aliases):
                updated += 1
            else:
                skipped += 1
        else:
            log.info(f"[AliasBackfill] {identity_id}: {aliases[:5]}")
            updated += 1
    print(json.dumps({"updated": updated, "skipped": skipped, "apply": args.apply}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
