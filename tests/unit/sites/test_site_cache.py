"""SiteCache 单元测试."""

from unittest.mock import MagicMock

import pytest  # noqa: F401

from app.services.site_rate_limiter import SiteRateLimiterService
from app.sites.site_cache import SiteCache

_Entity = MagicMock


class _Entity:
    def __init__(self, eid, name, note=None, rss_url="", sign_url="", cookie=""):
        self.id = eid
        self.name = name
        self.note = note or {}
        self.rss_url = rss_url
        self.sign_url = sign_url
        self.cookie = cookie
        self.api_key = None
        self.bearer_token = None
        self.headers = None
        self.rss_uses = "D"
        self.pri = 0


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.list_all.return_value = []
    return repo


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.get_by_url.return_value = None
    return engine


class TestSiteCache:
    def test_check_ratelimit_reuses_limiter(self, mock_repo, mock_engine):
        limiter = MagicMock(spec=SiteRateLimiterService)
        limiter.check.return_value = True
        cache = SiteCache(repo=mock_repo, site_engine=mock_engine, rate_limiter=limiter)
        assert cache.check_ratelimit(1) is True
        assert cache.check_ratelimit(1) is True
        limiter.check.assert_called_with("1", timeout=0)
        assert limiter.check.call_count == 2

    def test_register_site_on_refresh(self, mock_repo, mock_engine):
        limiter = MagicMock(spec=SiteRateLimiterService)
        mock_repo.list_all.return_value = [_Entity(1, "s1", note={"limit_interval": 60, "limit_count": 10})]
        SiteCache(repo=mock_repo, site_engine=mock_engine, rate_limiter=limiter)
        limiter.register_site.assert_called_once_with("1", {"limit_interval": 60, "limit_count": 10})

    def test_build_site_info_reads_boolean_switches(self, mock_repo, mock_engine):
        limiter = MagicMock(spec=SiteRateLimiterService)
        mock_repo.list_all.return_value = [
            _Entity(
                1,
                "s1",
                note={
                    "parse": True,
                    "message": False,
                    "chrome": True,
                    "proxy": False,
                    "subtitle": True,
                    "tag": True,
                    "public": False,
                },
                rss_url="https://example.com/rss",
                cookie="c=1",
            )
        ]
        cache = SiteCache(repo=mock_repo, site_engine=mock_engine, rate_limiter=limiter)
        site = cache.get_sites(siteid=1)
        assert isinstance(site, dict)
        assert site["parse"] is True
        assert site["unread_msg_notify"] is False
        assert site["chrome"] is True
        assert site["proxy"] is False
        assert site["subtitle"] is True
        assert site["tag"] == "s1"
        assert site["public"] is False

    def test_build_site_info_tag_enabled_returns_site_name(self, mock_repo, mock_engine):
        limiter = MagicMock(spec=SiteRateLimiterService)
        mock_repo.list_all.return_value = [_Entity(1, "站点A", note={"tag": True}, rss_url="https://example.com/rss")]
        cache = SiteCache(repo=mock_repo, site_engine=mock_engine, rate_limiter=limiter)
        site = cache.get_sites(siteid=1)
        assert isinstance(site, dict)
        assert site["tag"] == "站点A"
