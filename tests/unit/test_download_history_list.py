"""近期下载列表：按统一身份去重并保持时间倒序。"""

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.engine import get_engine
from app.db.models import DOWNLOADHISTORY, Base
from app.db.repositories.download_repository import DownloadRepository


@pytest.fixture(autouse=True)
def _clean_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def _row(
    date: str,
    *,
    title: str = "t",
    tmdb: str = "",
    se: str = "",
    identity: str | None = None,
    anchor_provider: str | None = None,
    anchor_external_id: str | None = None,
):
    return DOWNLOADHISTORY(
        TITLE=title,
        YEAR="",
        TYPE="MOVIE",
        TMDBID=tmdb,
        ANCHOR_PROVIDER=anchor_provider,
        ANCHOR_EXTERNAL_ID=anchor_external_id,
        IDENTITY_ID=identity,
        SE=se,
        VOTE="",
        POSTER="",
        OVERVIEW="",
        TORRENT="",
        ENCLOSURE="",
        SITE="",
        DESC="",
        DOWNLOADER="d",
        DOWNLOAD_ID=f"x-{title}",
        SAVE_PATH="/p",
        STATE="completed",
        DATE=date,
    )


def test_recent_downloads_keep_distinct_non_tmdb_items_in_time_order():
    session = sessionmaker(bind=get_engine())()
    session.add_all(
        [
            _row("2026-11-02 09:00:00", title="A-old", identity="id-a"),
            _row("2026-11-02 12:00:00", title="A-new", identity="id-a"),
            _row("2026-11-02 11:00:00", title="B", identity="id-b"),
            _row("2026-10-31 10:00:00", title="EP1", tmdb="100", se="S01E01"),
            _row("2026-10-31 10:00:00", title="EP2", tmdb="100", se="S01E02"),
            _row(
                "2026-10-30 10:00:00",
                title="anchor-only",
                anchor_provider="provider",
                anchor_external_id="X-1",
            ),
            _row("2026-10-29 10:00:00", title="legacy-only"),
        ]
    )
    session.commit()
    session.close()

    rows = DownloadRepository().get_download_history(num=30, page=1)

    titles = [row.TITLE for row in rows]
    assert "A-old" not in titles
    assert {"A-new", "B", "EP1", "EP2", "anchor-only", "legacy-only"} <= set(titles)
    assert [row.DATE for row in rows] == sorted([row.DATE for row in rows], reverse=True)
