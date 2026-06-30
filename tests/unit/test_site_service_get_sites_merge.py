"""
SiteService.get_sites() 第三方站点合并测试
"""

from unittest.mock import MagicMock

import pytest

from app.domain.entities.indexer_site_config import IndexerSiteConfigEntity
from app.services.site_service import SiteService


@pytest.fixture
def site_service_with_third_party():
    sites = MagicMock()
    sites.get_sites.return_value = [
        {
            "id": 1,
            "name": "M-Team",
            "pri": 1,
            "rssurl": "",
            "signurl": "",
            "cookie": "",
            "download_setting": 1,
            "enabled": True,
            "public": False,
        }
    ]
    sites.get_site_dict.return_value = [{"id": 1, "name": "M-Team"}]

    repo = MagicMock()
    repo.list_all.return_value = [
        IndexerSiteConfigEntity(id=10, site_name="1337x", source="jackett", enabled=True, public=True),
        IndexerSiteConfigEntity(id=11, site_name="M-Team", source="jackett", enabled=True, public=False),
    ]

    svc = SiteService(
        sites=sites,
        site_user_info=MagicMock(),
        site_conf=MagicMock(),
        indexer_service=MagicMock(),
        site_repo=MagicMock(),
        site_favicon_service=MagicMock(),
        site_resolver=MagicMock(),
        site_cookie=MagicMock(),
        string_utils=MagicMock(),
        site_entity_repo=MagicMock(),
        indexer_site_config_repo=repo,
    )
    return svc


class TestSiteServiceGetSitesMerge:
    def test_basic_mode_merges_builtin_and_third_party(self, site_service_with_third_party):
        result = site_service_with_third_party.get_sites(basic=True)
        names = {r["name"] for r in result}
        assert names == {"M-Team", "1337x"}
        third_party = [r for r in result if r.get("third_party")]
        assert len(third_party) == 1
        assert third_party[0]["source"] == "jackett"

    def test_basic_mode_builtin_takes_precedence_for_same_name(self, site_service_with_third_party):
        result = site_service_with_third_party.get_sites(basic=True)
        mteam = [r for r in result if r["name"] == "M-Team"][0]
        assert mteam.get("source") == "builtin"
        assert mteam.get("third_party") is None

    def test_full_mode_returns_default_fields_for_third_party(self, site_service_with_third_party):
        result = site_service_with_third_party.get_sites(basic=False)
        third_party = [r for r in result if r.get("third_party")]
        assert len(third_party) == 1
        tp = third_party[0]
        assert tp["name"] == "1337x"
        assert tp["source"] == "jackett"
        assert tp["public"] is True
        assert tp["rssurl"] == ""
        assert tp["rss_enable"] is False

    def test_rss_brush_statistic_filter_returns_only_builtin(self, site_service_with_third_party):
        for flag in ("rss", "brush", "statistic"):
            site_service_with_third_party.get_sites(**{flag: True})
            site_service_with_third_party._sites.get_sites.assert_called_with(
                rss=(flag == "rss"),
                brush=(flag == "brush"),
                statistic=(flag == "statistic"),
                public=True,
            )
