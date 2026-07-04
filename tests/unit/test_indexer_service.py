"""Tests for app.services.indexer_service."""

from unittest.mock import MagicMock

from app.domain.entities.indexer_config import IndexerConfigEntity
from app.domain.entities.indexer_site_config import IndexerSiteConfigEntity
from app.services.indexer_service import IndexerService


def _make_service(
    site_config_repo=None,
    idx_config_repo=None,
):
    return IndexerService(
        indexer=MagicMock(),
        indexer_helper=MagicMock(),
        site_cache=MagicMock(),
        site_engine=MagicMock(),
        indexer_statistics_repo=MagicMock(),
        string_utils=MagicMock(),
        site_config_repo=site_config_repo,
        idx_config_repo=idx_config_repo,
    )


class TestIndexerServiceGetUserIndexerNames:
    """Test suite for get_user_indexer_names."""

    def test_returns_builtin_names_when_enabled(self):
        site_config_repo = MagicMock()
        site_config_repo.list_enabled_names.return_value = ["site1", "site2"]
        site_config_repo.list_all.return_value = []
        idx_config_repo = MagicMock()
        idx_config_repo.get_by_client_id.return_value = IndexerConfigEntity(client_id="builtin", enabled=True)

        svc = _make_service(site_config_repo=site_config_repo, idx_config_repo=idx_config_repo)
        result = svc.get_user_indexer_names()

        assert result == ["site1", "site2"]
        site_config_repo.list_enabled_names.assert_called_once_with(source="builtin")
        idx_config_repo.get_by_client_id.assert_called_with("builtin")

    def test_skips_builtin_when_disabled(self):
        site_config_repo = MagicMock()
        site_config_repo.list_enabled_names.return_value = ["site1"]
        site_config_repo.list_all.return_value = []
        idx_config_repo = MagicMock()
        idx_config_repo.get_by_client_id.return_value = IndexerConfigEntity(client_id="builtin", enabled=False)

        svc = _make_service(site_config_repo=site_config_repo, idx_config_repo=idx_config_repo)
        result = svc.get_user_indexer_names()

        assert result == []
        site_config_repo.list_enabled_names.assert_not_called()

    def test_includes_enabled_third_party_sites(self):
        site_config_repo = MagicMock()
        site_config_repo.list_enabled_names.return_value = []
        site_config_repo.list_all.return_value = [
            IndexerSiteConfigEntity(site_name="jackett-site", source="jackett", enabled=True),
        ]
        idx_config_repo = MagicMock()

        def _get_by_client_id(client_id: str):
            if client_id == "builtin":
                return IndexerConfigEntity(client_id="builtin", enabled=True)
            if client_id == "jackett":
                return IndexerConfigEntity(client_id="jackett", enabled=True)
            return None

        idx_config_repo.get_by_client_id.side_effect = _get_by_client_id

        svc = _make_service(site_config_repo=site_config_repo, idx_config_repo=idx_config_repo)
        result = svc.get_user_indexer_names()

        assert "jackett-site" in result

    def test_excludes_disabled_third_party_client(self):
        site_config_repo = MagicMock()
        site_config_repo.list_enabled_names.return_value = []
        site_config_repo.list_all.return_value = [
            IndexerSiteConfigEntity(site_name="prowlarr-site", source="prowlarr", enabled=True),
        ]
        idx_config_repo = MagicMock()

        def _get_by_client_id(client_id: str):
            if client_id == "builtin":
                return IndexerConfigEntity(client_id="builtin", enabled=True)
            if client_id == "prowlarr":
                return IndexerConfigEntity(client_id="prowlarr", enabled=False)
            return None

        idx_config_repo.get_by_client_id.side_effect = _get_by_client_id

        svc = _make_service(site_config_repo=site_config_repo, idx_config_repo=idx_config_repo)
        result = svc.get_user_indexer_names()

        assert "prowlarr-site" not in result

    def test_deduplicates_case_insensitively(self):
        site_config_repo = MagicMock()
        site_config_repo.list_enabled_names.return_value = ["SiteA"]
        site_config_repo.list_all.return_value = [
            IndexerSiteConfigEntity(site_name="sitea", source="jackett", enabled=True),
        ]
        idx_config_repo = MagicMock()

        def _get_by_client_id(client_id: str):
            if client_id == "builtin":
                return IndexerConfigEntity(client_id="builtin", enabled=True)
            if client_id == "jackett":
                return IndexerConfigEntity(client_id="jackett", enabled=True)
            return None

        idx_config_repo.get_by_client_id.side_effect = _get_by_client_id

        svc = _make_service(site_config_repo=site_config_repo, idx_config_repo=idx_config_repo)
        result = svc.get_user_indexer_names()

        assert result == ["SiteA"]

    def test_does_not_call_indexer_http(self):
        site_config_repo = MagicMock()
        site_config_repo.list_enabled_names.return_value = []
        site_config_repo.list_all.return_value = []
        idx_config_repo = MagicMock()
        idx_config_repo.get_by_client_id.return_value = IndexerConfigEntity(client_id="builtin", enabled=True)
        indexer = MagicMock()

        svc = IndexerService(
            indexer=indexer,
            indexer_helper=MagicMock(),
            site_cache=MagicMock(),
            site_engine=MagicMock(),
            indexer_statistics_repo=MagicMock(),
            string_utils=MagicMock(),
            site_config_repo=site_config_repo,
            idx_config_repo=idx_config_repo,
        )
        svc.get_user_indexer_names()

        indexer.get_all_search_indexers.assert_not_called()
        indexer.get_indexers.assert_not_called()
