"""回填历史记录中缺失的 IDENTITY_ID.

优先按 anchor 解析/创建 MEDIA_IDENTITY + MEDIA_EXTERNAL_REF；
无 anchor 的下载/转移记录使用稳定本地兜底身份。
"""

from __future__ import annotations

from sqlalchemy import or_

from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.utils.identity import fallback_identity


def _missing(value) -> bool:
    return value is None or str(value).strip() == ""


def _media_type(value) -> str:
    key = str(value or "").lower()
    return {"mov": "movie", "movie": "movie", "tv": "tv", "ani": "anime", "anime": "anime"}.get(key, "movie")


def backfill() -> dict[str, int]:
    repo = MediaIdentityRepository()
    counts = {"search": 0, "download": 0, "transfer": 0}
    with BaseRepository().session() as db:
        # 搜索：按 distinct anchor 解析，批量更新同 anchor 的所有行
        anchors = (
            db.query(
                SEARCHRESULTINFO.ANCHOR_PROVIDER,
                SEARCHRESULTINFO.ANCHOR_EXTERNAL_ID,
                SEARCHRESULTINFO.CONTENT_PROFILE,
                SEARCHRESULTINFO.TYPE,
                SEARCHRESULTINFO.TITLE,
                SEARCHRESULTINFO.YEAR,
            )
            .filter(
                or_(SEARCHRESULTINFO.IDENTITY_ID.is_(None), SEARCHRESULTINFO.IDENTITY_ID == ""),
                SEARCHRESULTINFO.ANCHOR_PROVIDER.isnot(None),
                SEARCHRESULTINFO.ANCHOR_PROVIDER != "",
                SEARCHRESULTINFO.ANCHOR_EXTERNAL_ID.isnot(None),
                SEARCHRESULTINFO.ANCHOR_EXTERNAL_ID != "",
            )
            .distinct()
            .all()
        )
        cache: dict[tuple[str, str], str] = {}
        for provider, external_id, profile, mediatype, title, year in anchors:
            key = (str(provider), str(external_id))
            if key not in cache:
                cache[key] = repo.ensure_identity_for_ref(
                    key[0],
                    key[1],
                    media_type=_media_type(mediatype),
                    content_profile=str(profile or "default"),
                    title=title,
                    year=year,
                )
            identity_id = cache[key]
            if not identity_id:
                continue
            counts["search"] += (
                db.query(SEARCHRESULTINFO)
                .filter(
                    SEARCHRESULTINFO.ANCHOR_PROVIDER == provider,
                    SEARCHRESULTINFO.ANCHOR_EXTERNAL_ID == external_id,
                    or_(SEARCHRESULTINFO.IDENTITY_ID.is_(None), SEARCHRESULTINFO.IDENTITY_ID == ""),
                )
                .update({"IDENTITY_ID": identity_id}, synchronize_session=False)
            )

        # 下载
        downloads = (
            db.query(DOWNLOADHISTORY)
            .filter(or_(DOWNLOADHISTORY.IDENTITY_ID.is_(None), DOWNLOADHISTORY.IDENTITY_ID == ""))
            .all()
        )
        for row in downloads:
            identity_id = ""
            if not _missing(row.ANCHOR_PROVIDER) and not _missing(row.ANCHOR_EXTERNAL_ID):
                identity_id = repo.ensure_identity_for_ref(
                    str(row.ANCHOR_PROVIDER),
                    str(row.ANCHOR_EXTERNAL_ID),
                    media_type=_media_type(row.TYPE),
                    content_profile=str(row.CONTENT_PROFILE or "default"),
                    title=row.TITLE,
                    year=row.YEAR,
                )
            if not identity_id:
                identity_id = fallback_identity(
                    row.TITLE,
                    _media_type(row.TYPE),
                    0,
                    str(row.ANCHOR_PROVIDER or ""),
                    str(row.ANCHOR_EXTERNAL_ID or ""),
                )
            row.IDENTITY_ID = identity_id
            counts["download"] += 1

        # 转移
        transfers = (
            db.query(TRANSFERHISTORY)
            .filter(or_(TRANSFERHISTORY.IDENTITY_ID.is_(None), TRANSFERHISTORY.IDENTITY_ID == ""))
            .all()
        )
        for row in transfers:
            identity_id = ""
            if not _missing(row.ANCHOR_PROVIDER) and not _missing(row.ANCHOR_EXTERNAL_ID):
                identity_id = repo.ensure_identity_for_ref(
                    str(row.ANCHOR_PROVIDER),
                    str(row.ANCHOR_EXTERNAL_ID),
                    media_type=_media_type(row.TYPE),
                    content_profile=str(row.CONTENT_PROFILE or "default"),
                    title=row.TITLE,
                    year=row.YEAR,
                )
            if not identity_id:
                identity_id = fallback_identity(
                    row.TITLE,
                    _media_type(row.TYPE),
                    0,
                    str(row.ANCHOR_PROVIDER or ""),
                    str(row.ANCHOR_EXTERNAL_ID or ""),
                )
            row.IDENTITY_ID = identity_id
            counts["transfer"] += 1

        db.commit()
    return counts


if __name__ == "__main__":
    print(backfill())
