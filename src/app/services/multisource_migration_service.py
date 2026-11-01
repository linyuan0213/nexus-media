"""多元数据锚点迁移：旧 TMDBID/DB:/BG: → ANCHOR_* + IDENTITY_ID.

适用升级到 ADR-025 后的旧库：
- 订阅表：DB:/BG: 从 TMDBID 拆到 anchor 字段，TMDBID 置 NULL
- 下载历史：DB:/BG: 置空 TMDBID，写 anchor + identity
- 转移历史：非 TMDB 锚点 TMDBID 置 0，写 anchor + identity
- 已有 anchor 但缺 identity 的行补 identity

默认 dry-run；--apply 才写库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.models.download import DOWNLOADHISTORY
from app.db.models.library_rename import LIBRARYMEDIAMETADATA
from app.db.models.subscribe import SubscribeMovies, SubscribeTvs
from app.db.models.transfer import TRANSFERHISTORY
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.domain.mediatypes import MediaType
from app.media.metadata.legacy import parse_legacy_ref
from app.utils import JsonUtils


@dataclass
class MigrationReport:
    dry_run: bool
    scanned: int = 0
    updated_subscriptions: int = 0
    updated_downloads: int = 0
    updated_transfers: int = 0
    updated_metadata: int = 0
    created_identities: int = 0
    skipped: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    skip_reasons: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "scanned": self.scanned,
            "updated_subscriptions": self.updated_subscriptions,
            "updated_downloads": self.updated_downloads,
            "updated_transfers": self.updated_transfers,
            "updated_metadata": self.updated_metadata,
            "created_identities": self.created_identities,
            "skipped": self.skipped,
            "source_counts": self.source_counts,
            "skip_reasons": self.skip_reasons,
            "errors": self.errors,
        }


class MultiSourceMigrationService(BaseRepository):
    """幂等的多元数据锚点迁移服务."""

    def __init__(self, identity_repo: MediaIdentityRepository | None = None):
        self._identity_repo = identity_repo or MediaIdentityRepository()

    def run(self, *, dry_run: bool = True, limit: int | None = None) -> MigrationReport:
        report = MigrationReport(dry_run=dry_run)
        with self._session_manager.transaction_scope() as db:
            rows: list[tuple[str, Any]] = []
            rows.extend(("subscribe_movies", row) for row in db.query(SubscribeMovies).all())
            rows.extend(("subscribe_tvs", row) for row in db.query(SubscribeTvs).all())
            rows.extend(("download_history", row) for row in db.query(DOWNLOADHISTORY).all())
            rows.extend(("transfer_history", row) for row in db.query(TRANSFERHISTORY).all())
            rows.extend(("library_metadata", row) for row in db.query(LIBRARYMEDIAMETADATA).all())
            if limit is not None:
                rows = rows[:limit]
            for source, row in rows:
                report.scanned += 1
                report.source_counts[source] = report.source_counts.get(source, 0) + 1
                try:
                    changed, created = self._migrate_row(source, row, dry_run=dry_run)
                    if changed:
                        if source.startswith("subscribe"):
                            report.updated_subscriptions += 1
                        elif source == "download_history":
                            report.updated_downloads += 1
                        elif source == "library_metadata":
                            report.updated_metadata += 1
                        else:
                            report.updated_transfers += 1
                    if created:
                        report.created_identities += 1
                except Exception as exc:  # noqa: BLE001 - 单行失败不阻断
                    report.errors.append(f"{source}:{getattr(row, 'ID', '?')}: {exc}")
                if not dry_run:
                    db.flush()

        if not dry_run:
            # session_scope 退出时统一提交
            pass
        return report

    def _migrate_row(self, source: str, row: Any, *, dry_run: bool) -> tuple[bool, bool]:
        if source == "library_metadata":
            return self._migrate_library_row(row, dry_run=dry_run)
        media_type = self._media_type(row)
        raw = str(getattr(row, "TMDBID", "") or "").strip()
        provider = str(getattr(row, "ANCHOR_PROVIDER", "") or "").strip()
        external = str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "").strip()

        if not provider or not external:
            ref = parse_legacy_ref(raw, media_type)
            if ref is None:
                return False, False
            provider, external = ref.provider, ref.external_id
        if not provider or not external:
            return False, False

        identity = self._identity_repo.find_by_ref(
            provider,
            external,
            media_type=media_type.value,
        )
        created = False
        if identity is None:
            if dry_run:
                changed = self._needs_update(source, row, provider, external)
                return changed, True
            identity = self._identity_repo.ensure_identity(
                media_type=media_type.value,
                content_profile=self._content_profile(row, provider),
                title=getattr(row, "NAME", None) or getattr(row, "TITLE", None),
                year=getattr(row, "YEAR", None),
            )
            self._identity_repo.upsert_ref(
                identity.IDENTITY_ID,
                provider=provider,
                external_id=external,
                media_type=media_type.value,
                confidence=1.0,
                link_method="legacy_migration",
                link_confidence=1.0,
                reviewed=True,
                is_primary=True,
            )
            created = True

        changed = self._needs_update(source, row, provider, external, identity)
        if not changed or dry_run:
            return changed, created

        row.ANCHOR_PROVIDER = provider
        row.ANCHOR_EXTERNAL_ID = external
        row.IDENTITY_ID = identity.IDENTITY_ID if identity is not None else None
        row.CONTENT_PROFILE = self._content_profile(row, provider)
        if source.startswith("subscribe"):
            row.TMDBID = external if provider == "tmdb" else None
            if provider != "tmdb" and not getattr(row, "METADATA_POLICY", None):
                row.METADATA_POLICY = "douban_primary" if provider == "douban" else "bangumi_primary"
        elif source == "download_history":
            row.TMDBID = "" if provider != "tmdb" else str(external)
        else:
            row.TMDBID = 0 if provider != "tmdb" else int(external)
        return True, created

    @staticmethod
    def _needs_update(source: str, row: Any, provider: str, external: str, identity=None) -> bool:
        if str(getattr(row, "ANCHOR_PROVIDER", "") or "") != provider:
            return True
        if str(getattr(row, "ANCHOR_EXTERNAL_ID", "") or "") != external:
            return True
        if not getattr(row, "IDENTITY_ID", None) and identity is not None:
            return True
        if source.startswith("subscribe"):
            current_tmdb = str(getattr(row, "TMDBID", "") or "")
            if provider != "tmdb" and getattr(row, "TMDBID", None) is not None:
                return True
            if provider == "tmdb" and current_tmdb != external:
                return True
        if source == "download_history":
            if provider != "tmdb" and str(getattr(row, "TMDBID", "") or ""):
                return True
            if provider == "tmdb" and str(getattr(row, "TMDBID", "") or "") != external:
                return True
        if source == "transfer_history":
            if provider != "tmdb" and int(getattr(row, "TMDBID", 0) or 0) != 0:
                return True
            if provider == "tmdb" and int(getattr(row, "TMDBID", 0) or 0) != int(external):
                return True
        return False

    def _migrate_library_row(self, row: Any, *, dry_run: bool) -> tuple[bool, bool]:
        media_type = self._media_type(row)
        raw = {}
        try:
            raw = JsonUtils.loads(row.RAW or "{}")
        except Exception:  # noqa: BLE001
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        provider = str(raw.get("anchor_provider") or "").strip()
        external = str(raw.get("anchor_external_id") or "").strip()
        raw_id = str(row.TMDBID or raw.get("tmdbid") or "").strip()
        if not provider or not external:
            ref = parse_legacy_ref(raw_id, media_type)
            if ref is not None:
                provider, external = ref.provider, ref.external_id
        if not provider or not external:
            return False, False
        identity = self._identity_repo.find_by_ref(
            provider,
            external,
            media_type=media_type.value,
        )
        created = False
        if identity is None:
            if dry_run:
                return True, True
            identity = self._identity_repo.ensure_identity(
                media_type=media_type.value,
                content_profile=str(raw.get("content_profile") or self._content_profile(row, provider)),
                title=row.TITLE or None,
                year=row.YEAR or None,
            )
            self._identity_repo.upsert_ref(
                identity.IDENTITY_ID,
                provider=provider,
                external_id=external,
                media_type=media_type.value,
                confidence=1.0,
                link_method="legacy_migration",
                link_confidence=1.0,
                reviewed=True,
                is_primary=True,
            )
            created = True
        changed = (
            str(raw.get("anchor_provider") or "") != provider
            or str(raw.get("anchor_external_id") or "") != external
            or str(raw.get("identity_id") or "") != (identity.IDENTITY_ID if identity else "")
            or (row.TMDBID or "") != (external if provider == "tmdb" else "")
        )
        if not changed or dry_run:
            return changed, created
        raw["anchor_provider"] = provider
        raw["anchor_external_id"] = external
        raw["identity_id"] = identity.IDENTITY_ID if identity else ""
        raw["content_profile"] = raw.get("content_profile") or self._content_profile(row, provider)
        if provider == "douban" and not raw.get("metadata_policy"):
            raw["metadata_policy"] = "douban_primary"
        elif provider == "bangumi" and not raw.get("metadata_policy"):
            raw["metadata_policy"] = "bangumi_primary"
        row.TMDBID = external if provider == "tmdb" else ""
        row.RAW = JsonUtils.dumps(raw, ensure_ascii=False)
        return True, created

    @staticmethod
    def _media_type(row: Any) -> MediaType:
        table = str(getattr(row, "__tablename__", "") or "").upper()
        if "SUBSCRIBE_TVS" in table:
            profile = str(getattr(row, "CONTENT_PROFILE", "") or "").strip().lower()
            return MediaType.ANIME if profile == "anime" else MediaType.TV
        if "SUBSCRIBE_MOVIES" in table:
            return MediaType.MOVIE
        raw = str(getattr(row, "TYPE", "") or "").strip().lower()
        if raw in {"tv", "series", "show"} or "剧" in raw or "综艺" in raw:
            return MediaType.TV
        if raw in {"anime", "动画", "动漫"} or "动漫" in raw:
            return MediaType.ANIME
        return MediaType.MOVIE

    @staticmethod
    def _content_profile(row: Any, provider: str) -> str:
        current = str(getattr(row, "CONTENT_PROFILE", "") or "").strip()
        if current and current != "default":
            return current
        return "anime" if provider == "bangumi" else "default"
