"""为媒体库同步条目回填规范身份（仅解析，不为无锚点条目创建 local）."""

from __future__ import annotations

import re

from app.db.models.media_sync import MEDIASYNCITEMS
from app.db.repositories.base_repository import BaseRepository
from app.services.identity_resolver import IdentityResolver


def backfill() -> dict[str, int]:
    resolver = IdentityResolver()
    counts = {"scanned": 0, "updated": 0}
    with BaseRepository().session() as db:
        rows = (
            db.query(MEDIASYNCITEMS)
            .filter((MEDIASYNCITEMS.IDENTITY_ID.is_(None)) | (MEDIASYNCITEMS.IDENTITY_ID == ""))
            .all()
        )
        for row in rows:
            counts["scanned"] += 1
            provider = str(row.ANCHOR_PROVIDER or "").strip()
            external = str(row.ANCHOR_EXTERNAL_ID or "").strip()
            title_text = row.ORGIN_TITLE or row.TITLE
            if not provider and row.TMDBID:
                provider, external = "tmdb", str(row.TMDBID)
            elif not provider and row.IMDBID:
                provider, external = "imdb", str(row.IMDBID)
            elif not provider:
                match = re.search(r"([A-Za-z]{2,12})[-_ ]?(\d{2,6})", str(title_text or ""))
                if match:
                    provider = "content_id"
                    external = f"{match.group(1).upper()}-{match.group(2)}"
            item_type = str(row.ITEM_TYPE or "").lower()
            media_type = "movie" if item_type == "movie" else "tv"
            resolved = resolver.resolve_values(
                provider=provider,
                external_id=external,
                title=title_text,
                year=row.YEAR,
                media_type=media_type,
                content_profile=row.CONTENT_PROFILE,
                allow_local=False,
            )
            if resolved.identity_id:
                row.IDENTITY_ID = resolved.identity_id
                counts["updated"] += 1
        db.commit()
    return counts


if __name__ == "__main__":
    print(backfill())
