from unittest.mock import MagicMock

import pytest

from app.schemas.site import (
    SiteAttrDTO,
)
from app.services.site_service import SiteService


@pytest.fixture
def svc():
    mock_sites = MagicMock()
    mock_user_info = MagicMock()
    mock_conf = MagicMock()
    mock_cookie = MagicMock()
    mock_indexer = MagicMock()
    mock_str = MagicMock()
    return SiteService(
        sites=mock_sites,
        site_user_info=mock_user_info,
        site_conf=mock_conf,
        site_cookie=mock_cookie,
        indexer_service=mock_indexer,
        string_utils=mock_str,
    )


class TestCheckSiteAttr:
    def test_free(self, svc):
        svc._site_conf.get_grap_conf.return_value = {"FREE": True}
        dto = svc.check_site_attr("http://site.com")
        assert dto.site_free is True
        assert dto.site_2xfree is False
        assert dto.site_hr is False

    def test_all_attrs(self, svc):
        svc._site_conf.get_grap_conf.return_value = {"FREE": True, "2XFREE": True, "HR": True}
        dto = svc.check_site_attr("http://site.com")
        assert dto.site_free is True
        assert dto.site_2xfree is True
        assert dto.site_hr is True

    def test_empty(self, svc):
        svc._site_conf.get_grap_conf.return_value = {}
        dto = svc.check_site_attr(None)
        assert dto == SiteAttrDTO()


class TestDeleteSite:
    def test_with_id(self, svc):
        svc._sites.delete_site.return_value = 0
        assert svc.delete_site("1") == 0
        svc._sites.delete_site.assert_called_once_with("1")

    def test_without_id(self, svc):
        assert svc.delete_site(None) == 0
        svc._sites.delete_site.assert_not_called()


class TestGetSite:
    def test_with_id_and_attr(self, svc):
        svc._sites.get_sites.return_value = {"id": 1, "name": "A", "signurl": "http://s.com"}
        svc._site_conf.get_grap_conf.return_value = {"FREE": True}
        dto = svc.get_site("1")
        assert dto.site_free is True

    def test_without_id(self, svc):
        dto = svc.get_site(None)
        assert dto.site == []

    def test_no_signurl(self, svc):
        svc._sites.get_sites.return_value = {"id": 1, "name": "A"}
        dto = svc.get_site("1")
        assert dto.site_free is False


class TestGetSites:
    def test_basic(self, svc):
        svc._sites.get_site_dict.return_value = [{"id": 1, "name": "A"}]
        assert svc.get_sites(basic=True) == [{"id": 1, "name": "A"}]

    def test_full(self, svc):
        svc._sites.get_sites.return_value = [{"id": 1, "name": "A", "rss_enable": True}]
        assert svc.get_sites(rss=True) == [{"id": 1, "name": "A", "rss_enable": True}]


class TestUpdateSite:
    def test_add_success(self, svc):
        svc._sites.get_sites_by_name.return_value = []
        svc._sites.add_site.return_value = 0
        dto = svc.update_site(
            {
                "site_name": "New",
                "site_pri": 1,
                "site_rssurl": "",
                "site_signurl": "",
                "site_cookie": "",
                "site_note": {},
                "site_include": "D",
            }
        )
        assert dto.code == 0

    def test_duplicate_name(self, svc):
        svc._sites.get_sites_by_name.return_value = [{"id": 2, "name": "New"}]
        dto = svc.update_site({"site_id": "1", "site_name": "New"})
        assert dto.code == 400
        assert dto.msg == "站点名称重复"

    def test_update_not_found(self, svc):
        svc._sites.get_sites_by_name.return_value = []
        svc._sites.get_sites.return_value = {}
        dto = svc.update_site({"site_id": "99", "site_name": "New"})
        assert dto.code == 400
        assert dto.msg == "站点不存在"

    def test_update_success_with_rename(self, svc):
        svc._sites.get_sites_by_name.return_value = [{"id": 1, "name": "Old"}]
        svc._sites.get_sites.return_value = {"id": 1, "name": "Old"}
        svc._sites.update_site.return_value = 1
        dto = svc.update_site(
            {
                "site_id": "1",
                "site_name": "New",
                "site_pri": 1,
                "site_rssurl": "",
                "site_signurl": "",
                "site_cookie": "",
                "site_note": None,
                "site_include": "",
            }
        )
        assert dto.code == 1
        svc._site_user_info.update_site_name.assert_called_once_with("New", "Old")

    def test_update_no_rename(self, svc):
        svc._sites.get_sites_by_name.return_value = [{"id": 1, "name": "Same"}]
        svc._sites.get_sites.return_value = {"id": 1, "name": "Same"}
        svc._sites.update_site.return_value = 0
        dto = svc.update_site(
            {
                "site_id": "1",
                "site_name": "Same",
                "site_pri": 1,
                "site_rssurl": "",
                "site_signurl": "",
                "site_cookie": "",
                "site_note": None,
                "site_include": "",
            }
        )
        assert dto.code == 0
        svc._site_user_info.update_site_name.assert_not_called()


class TestUpdateSiteCookieUa:
    def test_ok(self, svc):
        svc.update_site_cookie_ua("1", "cookie", "ua")
        svc._sites.update_site_cookie.assert_called_once_with(siteid="1", cookie="cookie", ua="ua")


class TestGetSiteActivity:
    def test_ok(self, svc):
        svc._site_user_info.get_pt_site_activity_history.return_value = [["time", "upload"], [1, 2]]
        dto = svc.get_site_activity("s1")
        assert dto.dataset == [["time", "upload"], [1, 2]]


class TestGetSiteHistory:
    def test_ok(self, svc):
        svc._site_user_info.get_pt_site_statistics_history.return_value = (None, None, ["s1"], [100], [200])
        dto = svc.get_site_history(days=7)
        assert dto.dataset == [["site", "upload", "download"], ["s1", 100, 200]]


class TestGetSiteSeedingInfo:
    def test_ok(self, svc):
        svc._site_user_info.get_pt_site_seeding_info.return_value = {"seeding_info": [[1, "10GB"]]}
        dto = svc.get_site_seeding_info("s1")
        assert dto.dataset == [["seeders", "size"], [1, "10GB"]]


class TestGetSiteUserStatistics:
    def test_raw(self, svc):
        svc._site_user_info.get_site_user_statistics.return_value = [{"site": "s1", "url": "http://x.com"}]
        result = svc.get_site_user_statistics()
        assert len(result) == 1

    def test_mteam_fix(self, svc):
        svc._site_user_info.get_site_user_statistics.return_value = [{"site": "mt", "url": "https://m-team.io"}]
        svc._sites.get_sites.return_value = {"signurl": "https://xp.m-team.io"}
        result = svc.get_site_user_statistics()
        assert result[0]["url"] == "https://xp.m-team.io"

    def test_sort_asc(self, svc):
        svc._site_user_info.get_site_user_statistics.return_value = [
            {"site": "b", "upload": 200},
            {"site": "a", "upload": 100},
        ]
        result = svc.get_site_user_statistics(sort_by="upload", sort_on="asc")
        assert result[0]["site"] == "a"

    def test_sort_desc(self, svc):
        svc._site_user_info.get_site_user_statistics.return_value = [
            {"site": "a", "upload": 100},
            {"site": "b", "upload": 200},
        ]
        result = svc.get_site_user_statistics(sort_by="upload", sort_on="desc")
        assert result[0]["site"] == "b"

    def test_site_hash(self, svc):
        svc._site_user_info.get_site_user_statistics.return_value = [{"site": "s1"}]
        svc._string_utils.md5_hash.return_value = "abc123"
        result = svc.get_site_user_statistics(site_hash="Y")
        assert result[0]["site_hash"] == "abc123"


class TestGetSiteFavicon:
    def test_by_name(self, svc):
        svc._sites.get_site_favicon.return_value = b"icon"
        assert svc.get_site_favicon("s1") == b"icon"


class TestTestSite:
    def test_success(self, svc):
        svc._sites.test_connection.return_value = (True, "ok", 0.5)
        dto = svc.test_site("1")
        assert dto.flag is True
        assert dto.code == 0
        assert dto.msg == "ok"

    def test_fail(self, svc):
        svc._sites.test_connection.return_value = (False, "err", 0.0)
        dto = svc.test_site("1")
        assert dto.flag is False
        assert dto.code == -1


class TestSetCaptchaCode:
    def test_ok(self, svc):
        svc.set_captcha_code("code1", "val1")
        svc._site_cookie.set_code.assert_called_once_with(code="code1", value="val1")


class TestListSiteResources:
    def test_success(self, svc):
        from app.schemas.indexer import IndexerResourcesResultDTO

        svc._indexer_service.list_resources.return_value = IndexerResourcesResultDTO(
            success=True, data=[{"id": 1}], msg=""
        )
        dto = svc.list_site_resources("idx1", 0, "kw")
        assert dto.success is True
        assert dto.data == [{"id": 1}]

    def test_failure(self, svc):
        from app.schemas.indexer import IndexerResourcesResultDTO

        svc._indexer_service.list_resources.return_value = IndexerResourcesResultDTO(
            success=False, data=None, msg="无法连接到站点"
        )
        dto = svc.list_site_resources("idx1", 0, "kw")
        assert dto.success is False
        assert "无法连接到站点" in dto.msg
