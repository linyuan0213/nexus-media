"""修复订阅表中指向已删除/占位身份的记录."""

from __future__ import annotations

from app.db.models.media_identity import MediaExternalRef, MediaIdentity
from app.db.models.subscribe import SubscribeHistory, SubscribeMovies, SubscribeTvEpisodes, SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.services.identity_resolver import IdentityResolver


def repair() -> dict[str, int]:
    resolver = IdentityResolver()
    counts = {"scanned": 0, "repaired": 0, "unresolved": 0, "cleaned": 0}
    replaced_old: set[str] = set()
    with BaseRepository().session() as db:
        canonical = {str(row[0]) for row in db.query(MediaIdentity.IDENTITY_ID).all()}
        specs = ((SubscribeMovies, "movie"), (SubscribeTvs, "tv"))
        for model, media_type in specs:
            for row in db.query(model).all():
                counts["scanned"] += 1
                old_id = str(row.IDENTITY_ID or "")
                has_ref = bool(
                    db.query(MediaExternalRef.ID)
                    .filter(MediaExternalRef.IDENTITY_ID == old_id)
                    .first()
                )
                if old_id and old_id != "preview" and old_id in canonical and has_ref:
                    continue
                resolved = resolver.resolve_values(
                    identity_id=None,
                    provider=getattr(row, "ANCHOR_PROVIDER", None),
                    external_id=getattr(row, "ANCHOR_EXTERNAL_ID", None),
                    title=getattr(row, "NAME", None),
                    year=getattr(row, "YEAR", None),
                    media_type=media_type,
                    content_profile=getattr(row, "CONTENT_PROFILE", None),
                    allow_local=False,
                )
                if not resolved.identity_id:
                    counts["unresolved"] += 1
                    print("unresolved", model.__tablename__, row.ID, old_id, getattr(row, "ANCHOR_EXTERNAL_ID", None))
                    continue
                target_id = resolved.identity_id
                row.IDENTITY_ID = target_id
                for linked in (SubscribeHistory, SubscribeTvEpisodes):
                    db.query(linked).filter(linked.IDENTITY_ID == old_id).update(
                        {"IDENTITY_ID": target_id}, synchronize_session=False
                    )
                if old_id:
                    replaced_old.add(old_id)
                counts["repaired"] += 1
        db.flush()
        # 清理本次替换后不再被任何业务表引用的旧身份
        from app.db.models import DOWNLOADHISTORY, SEARCHRESULTINFO, TRANSFERHISTORY
        from app.db.models.lifecycle import MediaLifecycle

        for old_id in replaced_old:
            referenced = any(
                db.query(model).filter(model.IDENTITY_ID == old_id).first() is not None
                for model in (
                    SubscribeMovies,
                    SubscribeTvs,
                    SubscribeTvEpisodes,
                    SubscribeHistory,
                    DOWNLOADHISTORY,
                    TRANSFERHISTORY,
                    SEARCHRESULTINFO,
                    MediaLifecycle,
                )
            )
            if referenced or db.query(MediaExternalRef).filter(MediaExternalRef.IDENTITY_ID == old_id).first():
                continue
            db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == old_id).delete(synchronize_session=False)
            counts["cleaned"] += 1
        db.commit()
    return counts


if __name__ == "__main__":
    print(repair())
