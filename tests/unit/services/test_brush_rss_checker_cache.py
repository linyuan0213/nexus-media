"""BrushRssChecker 已处理缓存 TTL 单元测试."""

import time
from unittest.mock import MagicMock

from app.services.brush.rss_checker import _PROCESSED_CACHE_TTL, BrushRssChecker


def _make_checker() -> BrushRssChecker:
    return BrushRssChecker(
        helper=MagicMock(),
        media_service=MagicMock(),
        sites=MagicMock(),
        rsshelper=MagicMock(),
        siteconf=MagicMock(),
        torrents_cache={},
    )


class TestMarkOrSkipProcessed:
    def test_first_mark_returns_false(self):
        checker = _make_checker()
        assert checker._mark_or_skip_processed(1, "enc-1") is False
        assert "1:enc-1" in checker._torrents_cache

    def test_within_ttl_returns_true(self):
        checker = _make_checker()
        assert checker._mark_or_skip_processed(1, "enc-1") is False
        assert checker._mark_or_skip_processed(1, "enc-1") is True

    def test_expired_entry_allows_recheck(self, monkeypatch):
        checker = _make_checker()
        assert checker._mark_or_skip_processed(1, "enc-1") is False
        later = time.time() + _PROCESSED_CACHE_TTL + 1
        monkeypatch.setattr(time, "time", lambda: later)
        assert checker._mark_or_skip_processed(1, "enc-1") is False

    def test_eviction_removes_oldest_half(self):
        checker = _make_checker()
        now = time.time()
        checker._torrents_cache = {f"1:enc-{i}": now + i for i in range(10000)}
        assert checker._mark_or_skip_processed(1, "enc-new") is False
        assert len(checker._torrents_cache) == 5001
        assert "1:enc-0" not in checker._torrents_cache
        assert "1:enc-9999" in checker._torrents_cache
        assert "1:enc-new" in checker._torrents_cache

    def test_shared_dict_with_task_service(self):
        shared: dict[str, float] = {}
        checker = BrushRssChecker(
            helper=MagicMock(),
            media_service=MagicMock(),
            sites=MagicMock(),
            rsshelper=MagicMock(),
            siteconf=MagicMock(),
            torrents_cache=shared,
        )
        checker._mark_or_skip_processed(1, "enc-1")
        assert "1:enc-1" in shared


def test_torrent_attr_passes_chrome_flags(monkeypatch):
    """刷流属性抓取必须透传站点的 chrome/browser_persistent（否则 Cloudflare 站无法过盾）."""
    import app.services.brush.rss_checker as mod

    checker = _make_checker()
    monkeypatch.setattr(checker, "_rss_rule_needs_torrent_attr", lambda _rule: True)
    monkeypatch.setattr(mod, "cached_torrent_attr", lambda _url: None)
    monkeypatch.setattr(mod, "store_torrent_attr", lambda _url, _attr: None)
    captured: dict = {}
    monkeypatch.setattr(checker._siteconf, "check_torrent_attr", lambda **kwargs: captured.update(kwargs) or {})  # type: ignore[attr-defined]

    checker._check_torrent_attr_if_needed(
        rss_rule={},
        page_url="https://totheglory.im/details.php?id=1",
        cookie="c",
        api_key=None,
        bearer_token=None,
        ua="UA",
        headers={},
        site_proxy=False,
        chrome=True,
        browser_persistent=True,
    )

    assert captured["chrome"] is True
    assert captured["browser_persistent"] is True
