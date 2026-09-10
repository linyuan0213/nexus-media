"""HTML 搜索器：tbody 兜底与浏览器表单搜索回退测试."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from app.sites.html_searcher import HtmlSiteSearcher

_SITE_CFG = {
    "parser_type": "flat",
    "search": {"paths": [{"path": "torrents.php", "method": "get"}], "params": {"search": "{keyword}"}},
    "torrents": {
        "list": {"selector": 'table.torrents > tr:has("table.torrentname")'},
        "fields": {
            "title": {"selector": 'a[href*="details.php?id="]'},
        },
    },
}

_ROW_HTML = """
<table class="torrents"><tbody>
<tr><table class="torrentname"><tr><td>
  <a href="details.php?id=1">测试种子 A</a>
</td></tr></table></tr>
</tbody></table>
"""


def _searcher(chrome: bool = False):
    site = SimpleNamespace(
        html=_SITE_CFG,
        domain="https://example.test",
        name="示例站",
        encoding=None,
        api=None,
    )
    return HtmlSiteSearcher(
        cast(Any, site),
        site_engine=MagicMock(),
        user_config={"domain": "https://example.test", "ua": "UA", "chrome": chrome, "cookie": "c=1"},
    )


class TestTbodyFallback:
    def test_rows_in_tbody_matched_by_fallback(self):
        """选择器写 table > tr 但行在 tbody 内时，兜底补 tbody 命中"""
        searcher = _searcher()
        rows = searcher._parse_html(_ROW_HTML, is_browse=False)
        assert len(rows) == 1
        assert rows[0].get("title") == "测试种子 A"

    def test_no_rows_returns_empty(self):
        searcher = _searcher()
        assert searcher._parse_html("<html><body>无结果</body></html>", is_browse=False) == []


class TestBrowserFormSearchFallback:
    def test_form_search_used_when_direct_empty_and_chrome_enabled(self):
        searcher = _searcher(chrome=True)
        with (
            patch.object(searcher, "_fetch_html", return_value="<html>空壳</html>"),
            patch.object(searcher, "_browser_form_search", return_value=_ROW_HTML) as form_search,
        ):
            rows = searcher.search(keyword="测试", page=0)
        form_search.assert_called_once_with("测试")
        assert len(rows) == 1

    def test_no_form_search_when_chrome_disabled(self):
        searcher = _searcher(chrome=False)
        with (
            patch.object(searcher, "_fetch_html", return_value="<html>空壳</html>"),
            patch.object(searcher, "_browser_form_search", return_value=_ROW_HTML) as form_search,
        ):
            rows = searcher.search(keyword="测试", page=0)
        form_search.assert_not_called()
        assert rows == []
