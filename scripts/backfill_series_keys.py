"""将存量订阅/下载/转移/生命周期/历史迁移到内部 series_key（默认 dry-run）."""

from __future__ import annotations

import argparse
import re

import log
from app.db.models import DOWNLOADHISTORY, TRANSFERHISTORY, SubscribeHistory, SubscribeTorrents
from app.db.models.lifecycle import MediaLifecycle, MediaLifecycleEvent
from app.db.models.media_identity import MediaExternalRef, MediaIdentity
from app.db.models.subscribe import SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.services.series_service import SeriesService


def _season(value: str | None) -> int | None:
    text = str(value or "")
    match = re.search(r"[Ss](\d{1,2})", text) or re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*季", text)
    if not match:
        return None
    raw = match.group(1)
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    return mapping.get(raw) or int(raw)


def _ref(provider, external, metadata_ref=None, tmdbid=None) -> tuple[str, str]:
    provider = str(provider or "").strip()
    external = str(external or "").strip()
    if not external and metadata_ref and ":" in str(metadata_ref):
        provider, external = str(metadata_ref).split(":", 1)
    if not external and tmdbid:
        provider, external = "tmdb", str(tmdbid)
    return provider, external


def _resolve(service, provider, external, title, year, season, total, scope):
    base, parsed = service.split_title_season(title)
    season_num = int(season or parsed or 1)
    if not provider or not external:
        provider, external = "local", f"{base}:{year or ''}:S{season_num}"
    return service.resolve(
        provider=provider,
        external_id=external,
        title=str(title or ""),
        year=str(year or "") or None,
        season_number=season_num,
        scope=str(scope or "default"),
        total_episodes=total,
    )


def _apply_rows(rows, getter, service, apply: bool) -> tuple[int, int]:
    updated = skipped = 0
    for row in rows:
        provider, external, title, year, season, total, scope = getter(row)
        if not title:
            skipped += 1
            continue
        try:
            resolution = _resolve(service, provider, external, title, year, season, total, scope)
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            log.warn(f"[SeriesBackfill]解析失败 {type(row).__name__}#{row.ID}: {exc}")
            continue
        if apply:
            row.SERIES_KEY = resolution.series_key
        updated += 1
    return updated, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    service = SeriesService()
    repo = BaseRepository()
    report: dict[str, tuple[int, int]] = {}

    with repo.session() as db:
        report["subscribe_tvs"] = _apply_rows(
            db.query(SubscribeTvs).all(),
            lambda r: (
                *_ref(r.ANCHOR_PROVIDER, r.ANCHOR_EXTERNAL_ID, r.METADATA_REF, r.TMDBID),
                r.NAME,
                r.YEAR,
                _season(r.SEASON),
                r.TOTAL,
                r.CONTENT_PROFILE,
            ),
            service,
            args.apply,
        )
        report["subscribe_history"] = _apply_rows(
            db.query(SubscribeHistory).all(),
            lambda r: (
                *_ref(r.ANCHOR_PROVIDER, r.ANCHOR_EXTERNAL_ID, r.METADATA_REF, r.TMDBID),
                r.NAME,
                r.YEAR,
                _season(r.SEASON),
                r.TOTAL,
                r.CONTENT_PROFILE,
            ),
            service,
            args.apply,
        )
        report["subscribe_torrents"] = _apply_rows(
            db.query(SubscribeTorrents).all(),
            lambda r: (
                *_ref(r.ANCHOR_PROVIDER, r.ANCHOR_EXTERNAL_ID, None, None),
                r.TITLE,
                r.YEAR,
                _season(r.SEASON),
                None,
                r.CONTENT_PROFILE,
            ),
            service,
            args.apply,
        )
        report["download_history"] = _apply_rows(
            db.query(DOWNLOADHISTORY).all(),
            lambda r: (
                *_ref(r.ANCHOR_PROVIDER, r.ANCHOR_EXTERNAL_ID, None, r.TMDBID),
                r.TITLE,
                r.YEAR,
                _season(r.SE),
                None,
                r.CONTENT_PROFILE,
            ),
            service,
            args.apply,
        )
        report["transfer_history"] = _apply_rows(
            db.query(TRANSFERHISTORY).all(),
            lambda r: (
                *_ref(r.ANCHOR_PROVIDER, r.ANCHOR_EXTERNAL_ID, None, r.TMDBID),
                r.TITLE,
                r.YEAR,
                _season(r.SEASON_EPISODE),
                None,
                r.CONTENT_PROFILE,
            ),
            service,
            args.apply,
        )

        identity_map = {
            str(row.IDENTITY_ID): row.SERIES_KEY
            for row in db.query(SubscribeTvs).all()
            if row.IDENTITY_ID and row.SERIES_KEY
        }
        for row in db.query(DOWNLOADHISTORY).all():
            if row.IDENTITY_ID and row.SERIES_KEY:
                identity_map.setdefault(str(row.IDENTITY_ID), row.SERIES_KEY)
        for row in db.query(TRANSFERHISTORY).all():
            if row.IDENTITY_ID and row.SERIES_KEY:
                identity_map.setdefault(str(row.IDENTITY_ID), row.SERIES_KEY)

        identities = {str(row.IDENTITY_ID): row for row in db.query(MediaIdentity).all()}
        refs: dict[str, list[MediaExternalRef]] = {}
        for ref in db.query(MediaExternalRef).all():
            refs.setdefault(str(ref.IDENTITY_ID), []).append(ref)

        mapped = missed = 0
        for model in (MediaLifecycle, MediaLifecycleEvent):
            for row in db.query(model).all():
                identity_id = str(row.IDENTITY_ID)
                series_key = identity_map.get(identity_id)
                if not series_key:
                    identity = identities.get(identity_id)
                    if identity is not None and identity.CANONICAL_TITLE:
                        candidates = refs.get(identity_id, [])
                        preferred = next(
                            (ref for ref in candidates if ref.PROVIDER not in ("content_id", "tmdb")),
                            candidates[0] if candidates else None,
                        )
                        provider = preferred.PROVIDER if preferred else "local"
                        external = preferred.EXTERNAL_ID if preferred else ""
                        try:
                            resolution = _resolve(
                                service,
                                provider,
                                external,
                                identity.CANONICAL_TITLE,
                                identity.YEAR,
                                identity.SEASON_NUMBER,
                                None,
                                identity.CONTENT_PROFILE,
                            )
                        except Exception as exc:  # noqa: BLE001
                            log.warn(f"[SeriesBackfill]身份映射失败 {identity_id}: {exc}")
                        else:
                            series_key = resolution.series_key
                            identity_map[identity_id] = series_key
                if not series_key:
                    missed += 1
                    continue
                if args.apply:
                    row.SERIES_KEY = series_key
                mapped += 1
        report["lifecycle"] = (mapped, missed)

    for name, (updated, skipped) in report.items():
        log.info(f"[SeriesBackfill] {name}: 更新/可映射={updated} 跳过={skipped}")
    log.info(f"[SeriesBackfill] 完成 apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
