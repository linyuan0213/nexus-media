"""SearchRepository.insert_search_results 回归测试."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
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
    SearchRepository._session_manager = manager
    yield SearchRepository()
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
