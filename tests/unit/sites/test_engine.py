"""SiteEngine 单元测试."""

from app.sites.engine import SiteDefinition, SiteEngine


class TestSiteEngine:
    def test_get_by_url_uses_domain_index(self):
        engine = SiteEngine(definitions_dir="/nonexistent")
        site = SiteDefinition(id="t1", name="Test", domain="example.com", domain_aliases=["alias.org"])
        engine.register(site)

        assert engine.get_by_url("https://example.com/torrent/1") is site
        assert engine.get_by_url("https://alias.org/torrent/1") is site
        assert engine.get_by_url("https://unknown.com/torrent/1") is None

    def test_get_by_domain(self):
        engine = SiteEngine(definitions_dir="/nonexistent")
        site = SiteDefinition(id="t1", name="Test", domain="example.com")
        engine.register(site)
        assert engine.get_by_domain("example.com") is site
        assert engine.get_by_domain("EXAMPLE.COM") is site
        assert engine.get_by_domain("unknown.com") is None
