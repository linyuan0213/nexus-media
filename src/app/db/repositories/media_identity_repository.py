"""媒体身份、外部引用、快照与字段覆盖仓储."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.db.models.download import DOWNLOADHISTORY
from app.db.models.media_identity import (
    MediaExternalRef,
    MediaFieldOverride,
    MediaIdentity,
    MediaMetadataSnapshot,
)
from app.db.models.subscribe import SubscribeMovies, SubscribeTvs
from app.db.models.transfer import TRANSFERHISTORY
from app.db.repositories.base_repository import BaseRepository
from app.utils.ulid import new_ulid


class MediaIdentityRepository(BaseRepository):
    """ADR-025 身份与快照的数据库访问."""

    # ---------- identity ----------

    def set_parent(self, identity_id: str, parent_identity_id: str, season_number: int) -> bool:
        with self.session() as db:
            row = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == identity_id).first()
            if row is None:
                return False
            row.PARENT_IDENTITY_ID = parent_identity_id
            row.SEASON_NUMBER = season_number
            db.commit()
            return True

    def get_identity(self, identity_id: str) -> MediaIdentity | None:
        if not identity_id:
            return None
        with self.readonly() as db:
            return db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == identity_id).first()

    def ensure_identity(
        self,
        *,
        identity_id: str | None = None,
        media_type: str = "unknown",
        content_profile: str = "default",
        title: str | None = None,
        year: str | None = None,
        parent_identity_id: str | None = None,
        season_number: int | None = None,
    ) -> MediaIdentity:
        """按 ID 幂等创建；调用方也可指定稳定 ID."""
        target_id = identity_id or new_ulid()
        with self.session() as db:
            identity = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == target_id).first()
            if identity is None:
                identity = MediaIdentity(
                    IDENTITY_ID=target_id,
                    MEDIA_TYPE=media_type,
                    CONTENT_PROFILE=content_profile,
                    CANONICAL_TITLE=title,
                    YEAR=year,
                    PARENT_IDENTITY_ID=parent_identity_id,
                    SEASON_NUMBER=season_number,
                )
                db.add(identity)
                db.commit()
                db.refresh(identity)
                return identity
            changed = False
            if title and identity.CANONICAL_TITLE != title:
                identity.CANONICAL_TITLE = title
                changed = True
            if year and identity.YEAR != year:
                identity.YEAR = year
                changed = True
            if media_type and media_type != "unknown" and identity.MEDIA_TYPE != media_type:
                identity.MEDIA_TYPE = media_type
                changed = True
            if content_profile and identity.CONTENT_PROFILE != content_profile:
                identity.CONTENT_PROFILE = content_profile
                changed = True
            if changed:
                db.commit()
            return identity

    def find_by_ref(
        self,
        provider: str,
        external_id: str,
        *,
        scope: str = "default",
        media_type: str | None = None,
    ) -> MediaIdentity | None:
        with self.readonly() as db:
            ref = self._find_ref(db, provider, external_id, scope, media_type)
            if ref is None:
                return None
            return db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == ref.IDENTITY_ID).first()

    # ---------- refs ----------

    def upsert_ref(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        media_type: str | None = None,
        scope: str = "default",
        url: str | None = None,
        confidence: float = 1.0,
        link_method: str = "exact_ref",
        link_confidence: float = 1.0,
        reviewed: bool = False,
        is_primary: bool = False,
    ) -> MediaExternalRef:
        with self.session() as db:
            ref = self._find_ref(db, provider, external_id, scope, media_type)
            if ref is None:
                ref = MediaExternalRef(
                    IDENTITY_ID=identity_id,
                    PROVIDER=provider,
                    EXTERNAL_ID=str(external_id),
                    MEDIA_TYPE=media_type,
                    SCOPE=scope,
                    URL=url,
                    CONFIDENCE=confidence,
                    LINK_METHOD=link_method,
                    LINK_CONFIDENCE=link_confidence,
                    REVIEWED=int(reviewed),
                    IS_PRIMARY=int(is_primary),
                )
                db.add(ref)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    ref = self._find_ref(db, provider, external_id, scope, media_type)
                    if ref is None:
                        raise
                else:
                    db.refresh(ref)
                    return ref
            if ref.IDENTITY_ID != identity_id:
                raise ValueError(f"引用 {provider}:{external_id} 已属于其他身份 {ref.IDENTITY_ID}")
            ref.IDENTITY_ID = identity_id
            ref.MEDIA_TYPE = media_type or ref.MEDIA_TYPE
            ref.URL = url or ref.URL
            ref.CONFIDENCE = confidence
            ref.LINK_METHOD = link_method
            ref.LINK_CONFIDENCE = link_confidence
            ref.REVIEWED = int(bool(reviewed) or bool(ref.REVIEWED))
            ref.IS_PRIMARY = int(is_primary)
            db.commit()
            db.refresh(ref)
            return ref

    def list_pending_links(self, *, limit: int = 100) -> list[MediaExternalRef]:
        with self.readonly() as db:
            return (
                db.query(MediaExternalRef)
                .filter(MediaExternalRef.REVIEWED == 0)
                .order_by(MediaExternalRef.ID.desc())
                .limit(limit)
                .all()
            )

    def review_link(
        self,
        identity_id: str,
        *,
        provider: str,
        external_id: str,
        approve: bool,
        confidence: float = 1.0,
        scope: str = "default",
    ) -> MediaExternalRef | None:
        with self.session() as db:
            ref = self._find_ref(db, provider, external_id, scope)
            if ref is None or ref.IDENTITY_ID != identity_id:
                return None
            if not approve:
                db.delete(ref)
                db.commit()
                return None
            ref.REVIEWED = 1
            ref.LINK_CONFIDENCE = confidence
            db.commit()
            db.refresh(ref)
            return ref

    def merge_identity(self, source_id: str, target_id: str) -> bool:
        if source_id == target_id:
            return False
        with self.session() as db:
            source = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == source_id).first()
            target = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == target_id).first()
            if source is None or target is None:
                return False
            for ref in db.query(MediaExternalRef).filter(MediaExternalRef.IDENTITY_ID == source_id).all():
                ref.IDENTITY_ID = target_id
            db.query(MediaMetadataSnapshot).filter(MediaMetadataSnapshot.IDENTITY_ID == source_id).update(
                {"IDENTITY_ID": target_id}, synchronize_session=False
            )
            db.query(MediaFieldOverride).filter(MediaFieldOverride.IDENTITY_ID == source_id).update(
                {"IDENTITY_ID": target_id}, synchronize_session=False
            )
            for model in (SubscribeMovies, SubscribeTvs, DOWNLOADHISTORY, TRANSFERHISTORY):
                db.query(model).filter(model.IDENTITY_ID == source_id).update(
                    {"IDENTITY_ID": target_id}, synchronize_session=False
                )
            db.delete(source)
            db.commit()
            return True

    def list_refs(self, identity_id: str) -> list[MediaExternalRef]:
        with self.readonly() as db:
            return (
                db.query(MediaExternalRef)
                .filter(MediaExternalRef.IDENTITY_ID == identity_id)
                .order_by(MediaExternalRef.IS_PRIMARY.desc(), MediaExternalRef.ID.asc())
                .all()
            )

    # ---------- snapshots ----------

    def save_snapshot(
        self,
        identity_id: str,
        *,
        policy_key: str,
        content_profile: str,
        snapshot_hash: str,
        scope: str = "default",
        payload: dict[str, Any],
        providers: list[str] | None = None,
        status: str = "ok",
    ) -> MediaMetadataSnapshot:
        with self.session() as db:
            snapshot = MediaMetadataSnapshot(
                IDENTITY_ID=identity_id,
                POLICY_KEY=policy_key,
                CONTENT_PROFILE=content_profile,
                SCOPE=scope or "default",
                SNAPSHOT_HASH=snapshot_hash,
                PAYLOAD=json.dumps(payload, ensure_ascii=False),
                PROVIDERS=json.dumps(providers or [], ensure_ascii=False),
                STATUS=status,
                CREATED_AT=datetime.now(),
            )
            db.add(snapshot)
            db.commit()
            db.refresh(snapshot)
            return snapshot

    def latest_snapshot(
        self,
        identity_id: str,
        *,
        policy_key: str | None = None,
        scope: str | None = None,
    ) -> MediaMetadataSnapshot | None:
        with self.readonly() as db:
            query = db.query(MediaMetadataSnapshot).filter(MediaMetadataSnapshot.IDENTITY_ID == identity_id)
            if policy_key:
                query = query.filter(MediaMetadataSnapshot.POLICY_KEY == policy_key)
            if scope is not None:
                query = query.filter(MediaMetadataSnapshot.SCOPE == scope)
            return query.order_by(MediaMetadataSnapshot.ID.desc()).first()

    # ---------- overrides ----------

    def get_overrides(self, identity_id: str, *, user_id: int | None = None) -> list[MediaFieldOverride]:
        with self.readonly() as db:
            query = db.query(MediaFieldOverride).filter(MediaFieldOverride.IDENTITY_ID == identity_id)
            if user_id is None:
                query = query.filter(MediaFieldOverride.USER_ID.is_(None))
            else:
                query = query.filter(MediaFieldOverride.USER_ID == user_id)
            return query.all()

    def upsert_override(
        self,
        identity_id: str,
        *,
        field_name: str,
        value: str,
        user_id: int | None = None,
        provider: str | None = None,
        external_id: str | None = None,
        locale: str | None = None,
        locked: bool = True,
    ) -> MediaFieldOverride:
        with self.session() as db:
            query = db.query(MediaFieldOverride).filter(
                MediaFieldOverride.IDENTITY_ID == identity_id,
                MediaFieldOverride.FIELD_NAME == field_name,
            )
            query = query.filter(
                MediaFieldOverride.USER_ID.is_(None) if user_id is None else MediaFieldOverride.USER_ID == user_id
            )
            override = query.first()
            if override is None:
                override = MediaFieldOverride(
                    IDENTITY_ID=identity_id,
                    USER_ID=user_id,
                    FIELD_NAME=field_name,
                    VALUE=value,
                    PROVIDER=provider,
                    EXTERNAL_ID=external_id,
                    LOCALE=locale,
                    LOCKED=int(locked),
                )
                db.add(override)
            else:
                override.VALUE = value
                override.PROVIDER = provider
                override.EXTERNAL_ID = external_id
                override.LOCALE = locale
                override.LOCKED = int(locked)
            # 手动字段变化后旧快照失效
            db.query(MediaMetadataSnapshot).filter(MediaMetadataSnapshot.IDENTITY_ID == identity_id).delete(
                synchronize_session=False
            )
            db.commit()
            db.refresh(override)
            return override

    def _find_ref(
        self,
        db,
        provider: str,
        external_id: str,
        scope: str,
        media_type: str | None = None,
    ) -> MediaExternalRef | None:
        query = db.query(MediaExternalRef).filter(
            MediaExternalRef.PROVIDER == provider,
            MediaExternalRef.EXTERNAL_ID == str(external_id),
            MediaExternalRef.SCOPE == scope,
        )
        if media_type:
            typed = query.filter(MediaExternalRef.MEDIA_TYPE == media_type).first()
            if typed is not None:
                return typed
            # 兼容未回填类型的历史记录。
            return query.filter(MediaExternalRef.MEDIA_TYPE.is_(None)).first()
        return query.first()
