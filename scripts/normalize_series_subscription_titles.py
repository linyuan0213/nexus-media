"""把已映射剧集的订阅标题/关键词归一为母标题（默认 dry-run）."""

from __future__ import annotations

import argparse

import log
from app.db.models.media_series import MediaSeries
from app.db.models.subscribe import SubscribeTvs
from app.db.repositories.base_repository import BaseRepository
from app.services.series_service import SeriesService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    service = SeriesService()
    updated = 0
    with BaseRepository().session() as db:
        series = {row.SERIES_KEY: row for row in db.query(MediaSeries).all()}
        rows = db.query(SubscribeTvs).filter(SubscribeTvs.SERIES_KEY.is_not(None), SubscribeTvs.SERIES_KEY != "").all()
        for row in rows:
            canonical = series.get(row.SERIES_KEY)
            if canonical is None or not canonical.TITLE:
                continue
            old_name, old_keyword = row.NAME, row.KEYWORD
            base_keyword, _ = service.split_title_season(str(row.KEYWORD or row.NAME or ""))
            changed = row.NAME != canonical.TITLE or (
                bool(row.KEYWORD) and row.KEYWORD != (base_keyword or canonical.TITLE)
            )
            if not changed:
                continue
            log.info(
                f"[SeriesTitle]rssid={row.ID} name={old_name!r} keyword={old_keyword!r} "
                f"-> name={canonical.TITLE!r} keyword={(base_keyword or canonical.TITLE)!r}"
            )
            if args.apply:
                row.NAME = canonical.TITLE
                if row.KEYWORD:
                    row.KEYWORD = base_keyword or canonical.TITLE
            updated += 1
    log.info(f"[SeriesTitle]完成 apply={args.apply} 更新={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
