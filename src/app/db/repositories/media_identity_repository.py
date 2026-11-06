"""媒体身份、外部引用、快照与字段覆盖仓储."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import case, func
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


def _normalize_ref_media_type(media_type: str | None) -> str | None:
    """TMDB 等外部引用中 anime 与 tv 是同一实体，统一用 tv 做唯一键."""
    value = str(media_type or "").strip()
    if not value:
        return None
    return "tv" if value == "anime" else value


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

    @staticmethod
    def _decode_aliases(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def get_aliases(self, identity_id: str) -> list[str]:
        identity = self.get_identity(identity_id)
        return self._decode_aliases(getattr(identity, "ALIASES", None)) if identity is not None else []

    def get_aliases_map(self, identity_ids: list[str] | set[str]) -> dict[str, list[str]]:
        ids = [str(item) for item in identity_ids if item]
        if not ids:
            return {}
        with self.readonly() as db:
            rows = (
                db.query(MediaIdentity.IDENTITY_ID, MediaIdentity.ALIASES)
                .filter(MediaIdentity.IDENTITY_ID.in_(ids))
                .all()
            )
        return {str(identity_id): self._decode_aliases(raw) for identity_id, raw in rows}

    def replace_aliases(self, identity_id: str, aliases: list[str] | set[str]) -> bool:
        """用筛选后的别名替换身份别名，避免历史多语言列表持续膨胀."""
        if not identity_id:
            return False
        incoming = [str(item).strip() for item in aliases if str(item).strip()]
        with self.session() as db:
            row = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == identity_id).first()
            if row is None:
                return False
            existing = self._decode_aliases(row.ALIASES)
            if existing == incoming:
                return False
            row.ALIASES = json.dumps(incoming, ensure_ascii=False) if incoming else None
            db.commit()
            return True

    def update_aliases(self, identity_id: str, aliases: list[str] | set[str]) -> bool:
        if not identity_id:
            return False
        incoming = [str(item).strip() for item in aliases if str(item).strip()]
        if not incoming:
            return False
        with self.session() as db:
            row = db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == identity_id).first()
            if row is None:
                return False
            merged = self._decode_aliases(row.ALIASES)
            seen = {item.casefold() for item in merged}
            changed = False
            for alias in incoming:
                key = alias.casefold()
                if key not in seen:
                    seen.add(key)
                    merged.append(alias)
                    changed = True
            if changed:
                row.ALIASES = json.dumps(merged, ensure_ascii=False)
                db.commit()
            return changed

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
                db.expunge(identity)
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
                db.refresh(identity)
            db.expunge(identity)
            return identity

    def ensure_identity_for_ref(
        self,
        provider: str,
        external_id: str,
        *,
        scope: str = "default",
        media_type: str | None = None,
        content_profile: str = "default",
        title: str | None = None,
        year: str | None = None,
        url: str | None = None,
        link_method: str = "identity_boundary",
    ) -> str:
        """按外部引用查找身份；不存在时创建身份和 ref，返回 IDENTITY_ID."""
        provider = str(provider or "").strip()
        external_id = str(external_id or "").strip()
        if not provider or not external_id:
            return ""
        normalized_type = media_type if media_type and media_type != "unknown" else None
        found = self.find_by_ref(provider, external_id, scope=scope, media_type=normalized_type)
        if found is not None:
            return found.IDENTITY_ID
        identity = self.ensure_identity(
            media_type=normalized_type or "unknown",
            content_profile=content_profile or "default",
            title=title,
            year=year,
        )
        try:
            self.upsert_ref(
                identity.IDENTITY_ID,
                provider=provider,
                external_id=external_id,
                media_type=normalized_type,
                scope=scope,
                url=url,
                link_method=link_method,
                is_primary=True,
            )
        except ValueError:
            found = self.find_by_ref(provider, external_id, scope=scope, media_type=normalized_type)
            return found.IDENTITY_ID if found is not None else ""
        return identity.IDENTITY_ID

    def get_display_ref(self, identity_id: str) -> MediaExternalRef | None:
        """返回适合展示的来源引用：优先真实 provider，content_id 仅作最后兜底."""
        if not identity_id:
            return None
        with self.readonly() as db:
            return (
                db.query(MediaExternalRef)
                .filter(MediaExternalRef.IDENTITY_ID == identity_id)
                .order_by(
                    case((MediaExternalRef.PROVIDER == "content_id", 1), else_=0),
                    MediaExternalRef.IS_PRIMARY.desc(),
                    MediaExternalRef.ID.asc(),
                )
                .first()
            )

    def get_primary_ref(self, identity_id: str) -> MediaExternalRef | None:
        """返回身份的 primary ref（没有 primary 时取最早一条）."""
        if not identity_id:
            return None
        with self.readonly() as db:
            return (
                db.query(MediaExternalRef)
                .filter(MediaExternalRef.IDENTITY_ID == identity_id)
                .order_by(MediaExternalRef.IS_PRIMARY.desc(), MediaExternalRef.ID.asc())
                .first()
            )

    def find_by_external_id(
        self,
        external_id: str,
        *,
        media_type: str | None = None,
    ) -> MediaIdentity | None:
        """跨 provider 按外部编号查找身份（同一编号可能同时有内容锚点和真实 provider 引用）."""
        value = str(external_id or "").strip()
        if not value:
            return None
        normalized_type = _normalize_ref_media_type(media_type)
        with self.readonly() as db:
            query = db.query(MediaExternalRef).filter(MediaExternalRef.EXTERNAL_ID == value)
            if normalized_type:
                if normalized_type == "tv":
                    query = query.filter(MediaExternalRef.MEDIA_TYPE.in_(("tv", "anime")))
                else:
                    query = query.filter(MediaExternalRef.MEDIA_TYPE == normalized_type)
            ref = query.order_by(MediaExternalRef.IS_PRIMARY.desc(), MediaExternalRef.ID.asc()).first()
            if ref is None:
                return None
            return db.query(MediaIdentity).filter(MediaIdentity.IDENTITY_ID == ref.IDENTITY_ID).first()

    def find_by_title(
        self,
        title: str | None,
        year: str | None = None,
        media_type: str | None = None,
    ) -> MediaIdentity | None:
        """按标题/年份/类型查找已有身份，用于无 anchor 的下载/转移归并."""
        text = str(title or "").strip()
        if not text:
            return None
        # 动漫在部分历史数据中落为 tv，标题匹配时按同一类型族处理
        normalized_type = str(media_type or "")
        if normalized_type in {"anime", "tv"}:
            types: tuple[str, ...] = ("anime", "tv")
        elif normalized_type:
            types = (normalized_type,)
        else:
            types = ()
        with self.readonly() as db:
            query = db.query(MediaIdentity).filter(MediaIdentity.CANONICAL_TITLE == text)
            if year:
                query = query.filter(MediaIdentity.YEAR == str(year))
            if types:
                query = query.filter(MediaIdentity.MEDIA_TYPE.in_(types))
            found = query.first()
            if found is not None:
                return found
            # 标题可能有空白/大小写差异，退回不区分大小写匹配
            query = db.query(MediaIdentity).filter(func.lower(MediaIdentity.CANONICAL_TITLE) == text.lower())
            if year:
                query = query.filter(MediaIdentity.YEAR == str(year))
            if types:
                query = query.filter(MediaIdentity.MEDIA_TYPE.in_(types))
            return query.first()

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
            if ref is None and scope != "default":
                # 同一外部实体可能先以 season/profile scope 创建；仍归属同一作品
                ref = self._find_ref(db, provider, external_id, "default", media_type)
            if ref is None:
                ref = (
                    db.query(MediaExternalRef)
                    .filter(
                        MediaExternalRef.PROVIDER == provider,
                        MediaExternalRef.EXTERNAL_ID == str(external_id),
                    )
                    .order_by(MediaExternalRef.IS_PRIMARY.desc(), MediaExternalRef.ID.asc())
                    .first()
                )
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
        media_type = _normalize_ref_media_type(media_type)
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
        media_type = _normalize_ref_media_type(media_type)
        query = db.query(MediaExternalRef).filter(
            MediaExternalRef.PROVIDER == provider,
            MediaExternalRef.EXTERNAL_ID == str(external_id),
            MediaExternalRef.SCOPE == scope,
        )
        if media_type:
            typed = query.filter(MediaExternalRef.MEDIA_TYPE == media_type).first()
            if typed is not None:
                return typed
            if media_type == "tv":
                # 兼容历史 anime 引用，避免再次创建重复身份
                legacy = query.filter(MediaExternalRef.MEDIA_TYPE == "anime").first()
                if legacy is not None:
                    return legacy
            # 兼容未回填类型的历史记录。
            return query.filter(MediaExternalRef.MEDIA_TYPE.is_(None)).first()
        return query.first()
