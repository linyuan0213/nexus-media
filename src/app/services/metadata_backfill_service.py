"""P2-2 旧数据回填：订阅/下载/转移历史 → MediaIdentity + MediaExternalRef."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.db.repositories.legacy_media_ref_repository import LegacyMediaRefRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.domain.mediatypes import MediaType
from app.media.metadata.legacy import parse_legacy_ref


@dataclass
class BackfillReport:
    dry_run: bool
    scanned: int = 0
    unique_refs: int = 0
    existing: int = 0
    created_identities: int = 0
    planned_identities: int = 0
    duplicates: int = 0
    skipped: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    skip_reasons: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "scanned": self.scanned,
            "unique_refs": self.unique_refs,
            "existing": self.existing,
            "created_identities": self.created_identities,
            "planned_identities": self.planned_identities,
            "duplicates": self.duplicates,
            "skipped": self.skipped,
            "source_counts": self.source_counts,
            "skip_reasons": self.skip_reasons,
            "errors": self.errors,
        }


class MetadataBackfillService:
    """幂等回填；dry_run 默认只统计不写库."""

    def __init__(
        self,
        *,
        legacy_repo: LegacyMediaRefRepository | None = None,
        identity_repo: MediaIdentityRepository | None = None,
    ) -> None:
        self._legacy_repo = legacy_repo or LegacyMediaRefRepository()
        self._identity_repo = identity_repo or MediaIdentityRepository()

    def run(self, *, dry_run: bool = True, limit: int | None = None) -> BackfillReport:
        report = BackfillReport(dry_run=dry_run)
        rows = self._legacy_repo.list_rows(limit=limit)
        seen: set[tuple[str, str, str, str]] = set()

        for row in rows:
            report.scanned += 1
            report.source_counts[row.source] = report.source_counts.get(row.source, 0) + 1
            ref = parse_legacy_ref(row.raw_id, MediaType.from_string(row.media_type))
            if ref is None:
                report.skipped += 1
                reason = "empty_or_unknown_id"
                report.skip_reasons[reason] = report.skip_reasons.get(reason, 0) + 1
                continue

            key = (ref.provider, ref.external_id, ref.scope, row.media_type)
            if key in seen:
                report.duplicates += 1
                continue
            seen.add(key)
            report.unique_refs += 1

            existing = self._identity_repo.find_by_ref(
                ref.provider,
                ref.external_id,
                scope=ref.scope,
                media_type=row.media_type,
            )
            if existing is not None:
                report.existing += 1
                continue

            if dry_run:
                report.planned_identities += 1
                continue

            try:
                identity = self._identity_repo.ensure_identity(
                    media_type=row.media_type,
                    content_profile="default",
                    title=row.title or None,
                    year=row.year,
                )
                self._identity_repo.upsert_ref(
                    identity.IDENTITY_ID,
                    provider=ref.provider,
                    external_id=ref.external_id,
                    media_type=row.media_type,
                    scope=ref.scope,
                    confidence=1.0,
                    link_method=f"legacy_{ref.provider}",
                    link_confidence=1.0,
                    reviewed=True,
                    is_primary=True,
                )
                report.created_identities += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断整批
                report.errors.append(f"{row.source}:{row.raw_id}: {exc}")

        return report
