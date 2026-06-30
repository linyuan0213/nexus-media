"""
IndexerSiteConfigRepository 单元测试
"""

from contextlib import contextmanager

import pytest

from app.db.models import INDEXERSITECONFIG
from app.db.repositories.indexer_site_config_repository import IndexerSiteConfigRepository


class _TestableIndexerSiteConfigRepository(IndexerSiteConfigRepository):
    """测试用 Repository，复用同一个 session 避免事务隔离问题。"""

    def __init__(self, session):
        self._test_session = session
        super().__init__()

    @contextmanager
    def session(self):
        yield self._test_session


@pytest.fixture
def repo(db_session):
    return _TestableIndexerSiteConfigRepository(db_session)


class TestIndexerSiteConfigRepositoryCRUD:
    def test_upsert_site_creates_new_row(self, repo, db_session):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        row = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="M-Team").first()
        assert row is not None
        assert row.SOURCE == "builtin"
        assert row.ENABLED == 1

    def test_upsert_site_does_not_override_source(self, repo, db_session):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        repo.upsert_site(site_name="M-Team", source="jackett", enabled=True)
        row = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="M-Team").first()
        assert row.SOURCE == "builtin"

    def test_upsert_site_updates_enabled_and_download_setting(self, repo, db_session):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=False, download_setting=3)
        row = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="M-Team").first()
        assert row.ENABLED == 0
        assert row.DOWNLOAD_SETTING == 3

    def test_get_by_name_returns_row(self, repo):
        repo.upsert_site(site_name="TNode", source="builtin", enabled=False)
        row = repo.get_by_name("TNode")
        assert row is not None
        assert row.SITE_NAME == "TNode"
        assert row.ENABLED == 0

    def test_list_all_filters_by_source_and_enabled(self, repo):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        repo.upsert_site(site_name="TNode", source="builtin", enabled=False)
        repo.upsert_site(site_name="1337x", source="jackett", enabled=True)

        builtin_enabled = repo.list_all(source="builtin", enabled=True)
        assert len(builtin_enabled) == 1
        assert builtin_enabled[0].SITE_NAME == "M-Team"

        third_party = repo.list_all(source="jackett")
        assert len(third_party) == 1
        assert third_party[0].SITE_NAME == "1337x"

    def test_list_enabled_names(self, repo):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        repo.upsert_site(site_name="TNode", source="builtin", enabled=False)
        repo.upsert_site(site_name="1337x", source="jackett", enabled=True)

        names = repo.list_enabled_names()
        assert set(names) == {"M-Team", "1337x"}

        builtin_names = repo.list_enabled_names(source="builtin")
        assert builtin_names == ["M-Team"]

    def test_update_enabled(self, repo, db_session):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        repo.update_enabled("M-Team", False)
        row = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="M-Team").first()
        assert row.ENABLED == 0

    def test_update_download_setting(self, repo, db_session):
        repo.upsert_site(site_name="M-Team", source="builtin", enabled=True)
        repo.update_download_setting("M-Team", 5)
        row = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="M-Team").first()
        assert row.DOWNLOAD_SETTING == 5

    def test_migrate_from_user_indexer_sites(self, repo, db_session):
        repo.migrate_from_user_indexer_sites(
            user_indexer_sites=[1],
            site_name_by_id={1: "M-Team", 2: "TNode"},
        )
        mteam = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="M-Team").first()
        tnode = db_session.query(INDEXERSITECONFIG).filter_by(SITE_NAME="TNode").first()
        assert mteam is not None and mteam.ENABLED == 1
        assert tnode is not None and tnode.ENABLED == 0
