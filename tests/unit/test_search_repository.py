"""SearchRepository.insert_search_results 回归测试."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from app.db.models import SEARCHRESULTINFO, Base
from app.db.repositories.media_identity_repository import MediaIdentityRepository
from app.db.repositories.search_repository import SearchRepository
from app.db.session import SessionManager
from app.domain.mediatypes import MediaType


def _make_media_item(index: int, page_url: str | None = None, site: str = "site-a"):
    item = MagicMock()
    item.type = MediaType.MOVIE
    item.org_string = f"torrent {index}"
    item.enclosure = ""
    item.description = f"desc {index}"
    item.title = f"Title {index}"
    item.year = "2024"
    item.get_season_string.return_value = ""
    item.get_episode_string.return_value = ""
    item.get_season_episode_string.return_value = ""
    item.vote_average = "0"
    item.get_backdrop_image.return_value = ""
    item.get_poster_image.return_value = ""
    item.tmdb_id = ""
    item.identity_id = None
    item.anchor_provider = None
    item.anchor_external_id = None
    item.content_profile = "default"
    item.metadata_policy = None
    item.naming_profile = None
    item.overview = ""
    item.resource_pix = ""
    item.resource_type = ""
    item.resource_effect = ""
    item.video_encode = ""
    item.res_order = "0"
    item.size = index
    item.seeders = index
    item.peers = index
    item.site = site
    item.site_order = "0"
    item.page_url = page_url or f"https://example.com/t/{index}"
    item.resource_team = ""
    item.upload_volume_factor = 1.0
    item.download_volume_factor = 1.0
    item.labels = []
    return item


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    manager = SessionManager()
    manager._engine = engine
    manager._factory = sessionmaker(bind=engine)
    original_search = SearchRepository._session_manager
    original_identity = MediaIdentityRepository._session_manager
    SearchRepository._session_manager = manager
    MediaIdentityRepository._session_manager = manager
    try:
        yield SearchRepository()
    finally:
        SearchRepository._session_manager = original_search
        MediaIdentityRepository._session_manager = original_identity
        engine.dispose()


class TestInsertSearchResults:
    def test_insert_all_unique_results(self, repo):
        session_id = "sess-299"
        items = [_make_media_item(i, site="site-a") for i in range(299)]

        repo.insert_search_results(items, ident_flag=False, title="test", session_id=session_id)

        rows = repo.get_search_results(session_id=session_id)
        assert len(rows) == 299

    def test_dedup_same_pageurl_site_session(self, repo):
        session_id = "sess-dup"
        items = [
            _make_media_item(1, page_url="https://example.com/same", site="site-a"),
            _make_media_item(2, page_url="https://example.com/same", site="site-a"),
        ]

        repo.insert_search_results(items, ident_flag=False, title="test", session_id=session_id)

        rows = repo.get_search_results(session_id=session_id)
        assert len(rows) == 1

    def test_insert_persists_metadata_scope(self, repo):
        session_id = "sess-scope"
        item = _make_media_item(1)
        item.tmdb_id = "1399"
        item.identity_id = "01IDENTITY"
        item.anchor_provider = "tmdb"
        item.anchor_external_id = "1399"
        item.content_profile = "default"
        item.metadata_policy = "tmdb_primary"
        item.naming_profile = "default"

        repo.insert_search_results([item], ident_flag=True, session_id=session_id)

        with repo.session() as db:
            row = db.query(SEARCHRESULTINFO).filter(SEARCHRESULTINFO.SEARCH_SESSION_ID == session_id).one()
            assert row.IDENTITY_ID == "01IDENTITY"
            assert row.ANCHOR_PROVIDER == "tmdb"
            assert row.ANCHOR_EXTERNAL_ID == "1399"
            assert row.CONTENT_PROFILE == "default"
            assert row.METADATA_POLICY == "tmdb_primary"
            assert row.NAMING_PROFILE == "default"

    def test_replace_previous_session_results(self, repo):
        session_id = "sess-replace"
        repo.insert_search_results(
            [_make_media_item(i) for i in range(10)], ident_flag=False, title="test", session_id=session_id
        )
        repo.insert_search_results(
            [_make_media_item(i) for i in range(100, 150)], ident_flag=False, title="test", session_id=session_id
        )

        rows = repo.get_search_results(session_id=session_id)
        assert len(rows) == 50


class TestBuildUpsertStmt:
    def test_postgres_infers_unique_index_not_constraint(self):
        # 唯一性由唯一索引提供，PostgreSQL 不能用 ON CONFLICT ON CONSTRAINT，否则报
        # constraint "uq_search_pageurl_site_session" for table "SEARCH_RESULT_INFO" does not exist
        stmt = SearchRepository._build_upsert_stmt(
            "postgresql",
            [{"PAGEURL": "https://example.com/t/1", "SITE": "site-a", "SEARCH_SESSION_ID": "sess"}],
        )
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert 'ON CONFLICT ("PAGEURL", "SITE", "SEARCH_SESSION_ID") DO UPDATE' in sql
        assert "ON CONSTRAINT" not in sql
