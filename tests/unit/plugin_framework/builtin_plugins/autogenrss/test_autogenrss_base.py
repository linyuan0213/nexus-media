from unittest.mock import MagicMock

from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenContext,
    SiteRssGenHandler,
    SiteRssGenResult,
)


class TestSiteRssGenResult:
    def test_success(self):
        r = SiteRssGenResult.success("test_site")
        assert r.ok is True
        assert "生成RSS成功" in r.msg

    def test_success_with_reason(self):
        r = SiteRssGenResult.success("test_site", "已生成")
        assert r.ok is True
        assert "已生成" in r.msg

    def test_fail(self):
        r = SiteRssGenResult.fail("test_site", "cookie失效")
        assert r.ok is False
        assert "生成RSS失败" in r.msg
        assert "cookie失效" in r.msg

    def test_custom(self):
        r = SiteRssGenResult.custom(True, "custom message")
        assert r.ok is True
        assert r.msg == "custom message"


class TestSiteRssGenContext:
    def test_from_site_info_without_engine(self):
        ctx = SiteRssGenContext.from_site_info(
            {"id": 1, "name": "test", "signurl": "https://test.com/rss", "cookie": "c"}
        )
        assert ctx.site_id == "1"
        assert ctx.site == "test"
        assert ctx.site_url == "https://test.com/rss"
        assert ctx.cookie == "c"

    def test_from_site_info_resolves_canonical_id(self):
        site_def = MagicMock()
        site_def.id = "hdhome"
        site_def.name = "家园"
        site_def.domain = "https://hdhome.org"
        engine = MagicMock()
        engine.get_by_url = MagicMock(return_value=site_def)

        ctx = SiteRssGenContext.from_site_info(
            {"id": 71, "name": "家园", "signurl": "https://hdhome.org/getrss.php"},
            site_engine=engine,
        )
        assert ctx.site_id == "hdhome"
        assert ctx.site == "家园"
        assert ctx.site_url == "https://hdhome.org/getrss.php"
        engine.get_by_url.assert_called_once()

    def test_from_site_info_fallback_by_name(self):
        site_def = MagicMock()
        site_def.id = "ourbits"
        site_def.name = "我堡"
        site_def.domain = "https://ourbits.club"
        engine = MagicMock()
        engine.get_by_url = MagicMock(return_value=None)
        engine.get_by_name = MagicMock(return_value=site_def)

        ctx = SiteRssGenContext.from_site_info(
            {"id": 3, "name": "我堡", "strict_url": "", "signurl": "", "rssurl": ""},
            site_engine=engine,
        )
        assert ctx.site_id == "ourbits"
        assert ctx.site == "我堡"
        assert ctx.site_url == "https://ourbits.club"

    def test_from_site_info_parses_headers_string(self):
        ctx = SiteRssGenContext.from_site_info({"id": 1, "name": "test", "headers": '{"x-api-key": "abc"}'})
        assert ctx.headers == {"x-api-key": "abc"}


class TestSiteRssGenHandler:
    def test_check_base_url_from_site_def(self):
        class DummyHandler(SiteRssGenHandler):
            def generate(self, ctx):
                return SiteRssGenResult.custom(True, "")

        site_def = MagicMock()
        site_def.domain = "https://example.com"
        ctx = SiteRssGenContext.from_site_info({"id": 1, "name": "test", "signurl": "http://old.com"})
        handler = DummyHandler(MagicMock())
        assert handler._resolve_base_url(site_def, ctx) == "https://example.com"

    def test_check_base_url_from_ctx(self):
        class DummyHandler(SiteRssGenHandler):
            def generate(self, ctx):
                return SiteRssGenResult.custom(True, "")

        ctx = SiteRssGenContext.from_site_info({"id": 1, "name": "test", "signurl": "https://example.com/path"})
        handler = DummyHandler(MagicMock())
        assert handler._resolve_base_url(None, ctx) == "https://example.com"
