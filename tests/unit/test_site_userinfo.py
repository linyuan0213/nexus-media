"""SiteUserInfo 单元测试."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.infrastructure.rate_limiter import MemoryTokenBucketBackend, RateLimitEngine
from app.infrastructure.thread import ThreadExecutor
from app.sites.site_userinfo import SiteUserInfo


class _MockSiteInfo:
    def __init__(self):
        self.site_name = ""
        self.site_favicon = None
        self.err_msg = ""
        self.upload = 1
        self.username = "u"
        self.user_level = "1"
        self.join_at = "2024-01-01"
        self.download = 2
        self.ratio = 3.0
        self.seeding = 4
        self.seeding_size = 5
        self.leeching = 6
        self.bonus = 7
        self.message_unread = 0
        self.message_unread_contents = []

    def site_schema(self):
        return "mock"

    def parse(self):
        pass


class TestSiteUserInfo:
    @pytest.fixture
    def site_userinfo(self):
        site_cache = MagicMock()
        site_cache.get_sites.return_value = []
        site_repo = MagicMock()
        site_favicon = MagicMock()
        site_engine = MagicMock()
        executor = ThreadExecutor(max_workers=2, name="site_refresh_test")
        rate_limiter = RateLimitEngine()
        return SiteUserInfo(
            site_cache=site_cache,
            site_repository=site_repo,
            site_favicon_service=site_favicon,
            site_engine=site_engine,
            thread_executor=executor,
            rate_limiter=rate_limiter,
        )

    def test_refresh_all_site_data_concurrent(self, site_userinfo):
        """并发刷新多个站点并聚合结果."""
        site_cache = site_userinfo._site_cache
        site_cache.get_sites.return_value = [
            {"id": "1", "name": "a", "strict_url": "https://a.com", "cookie": "c1", "headers": "{}"},
            {"id": "2", "name": "b", "strict_url": "https://b.com", "cookie": "c2", "headers": "{}"},
        ]

        def mock_build(*, site_name, **kwargs):
            info = _MockSiteInfo()
            info.site_name = site_name
            return info

        site_userinfo.build = mock_build

        site_userinfo._SiteUserInfo__refresh_all_site_data(force=True)

        assert len(site_userinfo._sites_data) == 2
        assert "a" in site_userinfo._sites_data
        assert "b" in site_userinfo._sites_data

    def test_refresh_all_site_data_exception_isolated(self, site_userinfo):
        """单个站点异常不影响其他站点."""
        site_cache = site_userinfo._site_cache
        site_cache.get_sites.return_value = [
            {"id": "1", "name": "ok", "strict_url": "https://ok.com", "cookie": "c", "headers": "{}"},
            {"id": "2", "name": "fail", "strict_url": "https://fail.com", "cookie": "c", "headers": "{}"},
        ]

        def mock_build(*, site_name, **kwargs):
            if site_name == "fail":
                raise ValueError("boom")
            info = _MockSiteInfo()
            info.site_name = site_name
            return info

        site_userinfo.build = mock_build

        site_userinfo._SiteUserInfo__refresh_all_site_data(force=True)

        assert "ok" in site_userinfo._sites_data
        assert "fail" not in site_userinfo._sites_data

    def test_refresh_site_data_with_limit(self, site_userinfo):
        """限流器会限制过快调用."""
        site_info = {"id": "1", "name": "a", "strict_url": "https://a.com", "cookie": "c", "headers": "{}"}

        call_count = [0]

        def mock_build(*, site_name, **kwargs):
            call_count[0] += 1
            info = _MockSiteInfo()
            info.site_name = site_name
            return info

        site_userinfo.build = mock_build
        # 使用内存后端确保测试隔离，并设置极低速率
        site_userinfo._rate_limiter = RateLimitEngine(backend=MemoryTokenBucketBackend())
        site_userinfo._SITE_REFRESH_RATE = "1/60s"

        # 第一次应成功
        result1 = site_userinfo._refresh_site_data_with_limit(site_info)
        assert result1 is not None
        # 紧接着第二次应被限流跳过
        result2 = site_userinfo._refresh_site_data_with_limit(site_info)
        assert result2 is None
        assert call_count[0] == 1

    def test_refresh_all_site_data_respects_last_update_time(self, site_userinfo):
        """非 force 且未指定站点时，已有 last_update_time 则跳过."""
        site_userinfo._last_update_time = datetime.now()
        site_userinfo._site_cache.get_sites.reset_mock()
        site_userinfo._SiteUserInfo__refresh_all_site_data(force=False)
        assert site_userinfo._site_cache.get_sites.call_count == 0
