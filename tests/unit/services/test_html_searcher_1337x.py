"""1337x HTML 解析兜底测试."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from app.sites.search.html_searcher import HtmlSiteSearcher


def test_torrent_link_fallback_parses_title():
    site = SimpleNamespace(
        name="1337x",
        domain="https://1337x.to",
        html={
            "parser_type": "flat",
            "torrents": {
                "list": {"selector": "table.table-list tbody tr"},
                "fields": {
                    "title": {"selector": "td.coll-1.name a:last-child"},
                    "details": {"selector": "td.coll-1.name a:last-child", "attribute": "href"},
                },
            },
        },
    )
    searcher = HtmlSiteSearcher(cast(Any, site), site_engine=MagicMock(), user_config={})
    html = """
    <table class="table-list"><tbody><tr>
      <td class="coll-1 name"><a href="/sub/1/">Movies</a><a href="/torrent/42/test/">Avengers</a><span>x</span></td>
    </tr></tbody></table>
    """
    rows = searcher._parse_html(html)
    assert rows[0]["title"] == "Avengers"
    assert rows[0]["page_url"] == "https://1337x.to/torrent/42/test/"
