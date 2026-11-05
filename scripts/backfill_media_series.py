"""为存量 TV/动漫订阅回填内部 series_key（默认 dry-run）."""

from __future__ import annotations

import argparse
import re

import log
from app.db.models.subscribe import SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.services.series_service import SeriesService


def _season_number(value: str | None) -> int | None:
    match = re.search(r"(\d{1,2})", str(value or ""))
    return int(match.group(1)) if match else None


def _provider_ref(row: SubscribeTvs) -> tuple[str, str]:
    provider = str(row.ANCHOR_PROVIDER or row.PROVIDER or "").strip()
    external = str(row.ANCHOR_EXTERNAL_ID or "").strip()
    if not external and row.METADATA_REF and ":" in row.METADATA_REF:
        provider, external = row.METADATA_REF.split(":", 1)
    if not external and row.TMDBID:
        provider, external = "tmdb", str(row.TMDBID)
    return provider, external


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写入数据库，默认只打印")
    args = parser.parse_args()

    service = SeriesService()
    repo = BaseRepository()
    updated = skipped = failed = 0
    with repo.session() as db:
        rows = (
            db.query(SubscribeTvs).filter((SubscribeTvs.SERIES_KEY.is_(None)) | (SubscribeTvs.SERIES_KEY == "")).all()
        )
        for row in rows:
            provider, external = _provider_ref(row)
            if not provider or not external:
                skipped += 1
                log.info(f"[SeriesBackfill]跳过无来源: rssid={row.ID} name={row.NAME}")
                continue
            try:
                resolution = service.resolve(
                    provider=provider,
                    external_id=external,
                    title=str(row.NAME or ""),
                    year=str(row.YEAR or "") or None,
                    season_number=_season_number(row.SEASON),
                    scope=str(row.CONTENT_PROFILE or "default"),
                    total_episodes=row.TOTAL,
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warn(f"[SeriesBackfill]解析失败 rssid={row.ID}: {exc}")
                continue
            log.info(
                f"[SeriesBackfill]rssid={row.ID} {row.NAME} -> {resolution.series_key} S{resolution.season_number:02d}"
            )
            if args.apply:
                row.SERIES_KEY = resolution.series_key
            updated += 1
    log.info(f"[SeriesBackfill]完成 apply={args.apply} 更新={updated} 跳过={skipped} 失败={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
