"""SiteService 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.services.site_service import SiteService


@pytest.fixture
def site_service():
    return SiteService(
        sites=MagicMock(),
        site_user_info=MagicMock(),
        site_conf=MagicMock(),
        indexer_service=MagicMock(),
        site_repo=MagicMock(),
        site_favicon_service=MagicMock(),
        site_resolver=MagicMock(),
        site_cookie=MagicMock(),
        string_utils=MagicMock(),
        site_entity_repo=MagicMock(),
    )


class TestSiteServiceUpdate:
    def test_update_site_computes_include_from_switches(self, site_service):
        site_service._site_entity_repo.get_by_id.return_value = MagicMock(name="OldSite")
        site_service.update_site(
            {
                "site_id": "1",
                "site_name": "Test",
                "site_pri": "1",
                "site_rssurl": "https://example.com/rss",
                "site_signurl": "https://example.com",
                "site_cookie": "",
                "site_api_key": "",
                "site_bearer_token": "token",
                "site_headers": "",
                "site_note": "{}",
                "rss_enable": True,
                "brush_enable": True,
                "statistic_enable": True,
            }
        )
        updated = site_service._site_entity_repo.update.call_args[0][0]
        assert updated.rss_uses == "DST"

    def test_update_site_falls_back_to_include_when_switches_missing(self, site_service):
        site_service._site_entity_repo.get_by_id.return_value = MagicMock(name="OldSite")
        site_service.update_site(
            {
                "site_id": "1",
                "site_name": "Test",
                "site_pri": "1",
                "site_rssurl": "https://example.com/rss",
                "site_signurl": "https://example.com",
                "site_cookie": "",
                "site_api_key": "",
                "site_bearer_token": "token",
                "site_headers": "",
                "site_note": "{}",
                "site_include": "DT",
            }
        )
        updated = site_service._site_entity_repo.update.call_args[0][0]
        assert updated.rss_uses == "DT"

    def test_update_site_disabled_switch_removes_include_letter(self, site_service):
        site_service._site_entity_repo.get_by_id.return_value = MagicMock(name="OldSite")
        site_service.update_site(
            {
                "site_id": "1",
                "site_name": "Test",
                "site_pri": "1",
                "site_rssurl": "https://example.com/rss",
                "site_signurl": "https://example.com",
                "site_cookie": "c=1",
                "site_api_key": "",
                "site_bearer_token": "",
                "site_headers": "",
                "site_note": "{}",
                "rss_enable": True,
                "brush_enable": False,
                "statistic_enable": True,
            }
        )
        updated = site_service._site_entity_repo.update.call_args[0][0]
        assert updated.rss_uses == "DT"

    def test_update_site_partial_switch_preserves_other_letters(self, site_service):
        site_service._site_entity_repo.get_by_id.return_value = MagicMock(name="OldSite", rss_uses="ST")
        site_service.update_site(
            {
                "site_id": "1",
                "site_name": "Test",
                "site_pri": "1",
                "site_rssurl": "https://example.com/rss",
                "site_signurl": "https://example.com",
                "site_cookie": "c=1",
                "site_api_key": "",
                "site_bearer_token": "",
                "site_headers": "",
                "site_note": "{}",
                "rss_enable": True,
            }
        )
        updated = site_service._site_entity_repo.update.call_args[0][0]
        assert "D" in updated.rss_uses
        assert "S" in updated.rss_uses
        assert "T" in updated.rss_uses

    def test_update_site_normalizes_note_switches_to_boolean(self, site_service):
        site_service._site_entity_repo.get_by_id.return_value = MagicMock(name="OldSite")
        site_service.update_site(
            {
                "site_id": "1",
                "site_name": "Test",
                "site_pri": "1",
                "site_rssurl": "https://example.com/rss",
                "site_signurl": "https://example.com",
                "site_cookie": "c=1",
                "site_api_key": "",
                "site_bearer_token": "",
                "site_headers": "",
                "site_note": '{"parse": "Y", "message": "N", "chrome": true, "proxy": false, "tag": "Y"}',
                "rss_enable": True,
                "brush_enable": True,
                "statistic_enable": True,
            }
        )
        updated = site_service._site_entity_repo.update.call_args[0][0]
        assert updated.note["parse"] is True
        assert updated.note["message"] is False
        assert updated.note["chrome"] is True
        assert updated.note["proxy"] is False
        assert updated.note["tag"] is True


class TestSiteServiceGet:
    def test_get_site_returns_cache_with_computed_switches(self, site_service):
        site_service._sites.get_sites.return_value = {
            "id": 1,
            "name": "Test",
            "rss_enable": True,
            "brush_enable": False,
            "statistic_enable": True,
            "parse": True,
            "chrome": False,
            "signurl": "https://example.com",
        }
        site_service._site_conf.get_grap_conf.return_value = {"FREE": True}
        result = site_service.get_site("1")
        assert result.site["rss_enable"] is True
        assert result.site["statistic_enable"] is True
        assert result.site_free is True
