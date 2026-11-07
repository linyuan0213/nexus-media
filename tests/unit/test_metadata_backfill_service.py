"""P2-2 回填服务测试（内存库，无网络）."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.models.download import DOWNLOADHISTORY
from app.db.models.subscribe import SubscribeMovies, SubscribeTvs
from app.db.models.transfer import TRANSFERHISTORY
from app.db.repositories.legacy_media_ref_repository import LegacyMediaRefRepository
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.db.session import SessionManager
from app.domain.media_types import ProviderMediaType
from app.media.metadata.legacy import parse_legacy_ref
from app.services.metadata_backfill_service import MetadataBackfillService


@pytest.fixture
def repos():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    manager = SessionManager()
    manager._engine = engine
    manager._factory = sessionmaker(bind=engine, expire_on_commit=False)
    MediaIdentityRepository._session_manager = manager
    LegacyMediaRefRepository._session_manager = manager
    yield engine
    engine.dispose()


def _seed(engine):
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(SubscribeMovies(NAME="肖申克的救赎", YEAR="1994", TMDBID="278"))
        db.add(SubscribeMovies(NAME="重复条目", YEAR="1994", TMDBID="278"))
        db.add(SubscribeTvs(NAME="最后生还者", YEAR="2023", TMDBID="DB:25848328", SEASON="1"))
        db.add(
            DOWNLOADHISTORY(
                TITLE="某电影",
                YEAR="2020",
                TYPE="movie",
                TMDBID="456",
                SE="",
                VOTE="",
                POSTER="",
                OVERVIEW="",
                TORRENT="",
                ENCLOSURE="",
                SITE="",
                DESC="",
                DOWNLOADER="",
                DOWNLOAD_ID="",
                SAVE_PATH="",
                STATE="done",
                DATE="2026-01-01",
            )
        )
        db.add(
            TRANSFERHISTORY(
                MODE="copy",
                TYPE="tv",
                CATEGORY="",
                TMDBID=0,
                TITLE="未识别",
                YEAR="",
                SEASON_EPISODE="",
                SOURCE="",
                SOURCE_PATH="",
                SOURCE_FILENAME="",
                DEST="",
                DEST_PATH="",
                DEST_FILENAME="",
                DATE="2026-01-01",
            )
        )
        db.commit()


def test_parse_legacy_ref_variants():
    cases = [
        ("278", ProviderMediaType.MOVIE, "tmdb", "278"),
        ("DB:1292052", ProviderMediaType.MOVIE, "douban", "1292052"),
        ("BG:400602", ProviderMediaType.ANIME, "bangumi", "400602"),
        ("BGM:1", ProviderMediaType.ANIME, "bangumi", "1"),
        ("TMDB:278", ProviderMediaType.MOVIE, "tmdb", "278"),
    ]
    for raw, media_type, provider, external_id in cases:
        ref = parse_legacy_ref(raw, media_type)
        assert ref is not None
        assert (ref.provider, ref.external_id) == (provider, external_id)

    assert parse_legacy_ref("0", ProviderMediaType.MOVIE) is None
    assert parse_legacy_ref("unknown", ProviderMediaType.MOVIE) is None


def test_dry_run_does_not_write(repos):
    _seed(repos)
    service = MetadataBackfillService()
    report = service.run(dry_run=True)

    assert report.scanned == 5
    assert report.unique_refs == 3  # 278 去重；DB:25848328；456
    assert report.planned_identities == 3
    assert report.duplicates == 1
    assert report.skipped == 1

    identity_repo = MediaIdentityRepository()
    assert identity_repo.find_by_ref("tmdb", "278") is None


def test_write_is_idempotent(repos):
    _seed(repos)
    service = MetadataBackfillService()

    first = service.run(dry_run=False)
    assert first.created_identities == 3
    assert first.errors == []

    identity = MediaIdentityRepository().find_by_ref("tmdb", "278")
    assert identity is not None
    refs = MediaIdentityRepository().list_refs(identity.IDENTITY_ID)
    assert [(ref.PROVIDER, ref.EXTERNAL_ID) for ref in refs] == [("tmdb", "278")]
    assert refs[0].LINK_METHOD == "legacy_tmdb"
    assert refs[0].REVIEWED == 1

    second = service.run(dry_run=False)
    assert second.created_identities == 0
    assert second.existing == 3
