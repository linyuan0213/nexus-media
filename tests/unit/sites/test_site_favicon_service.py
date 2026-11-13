"""站点图标解析优先级测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.sites.connectivity.site_favicon_service import SiteFaviconService


def _service(sites, all_sites, definitions_by_name=None):
    svc = SiteFaviconService.__new__(SiteFaviconService)
    svc._favicons = {}
    svc._cache = MagicMock()
    svc._cache.get_sites_by_name.return_value = sites
    svc._cache.get_sites.return_value = sites
    svc._site_engine = MagicMock()
    svc._site_engine.all_sites.return_value = all_sites
    svc._site_engine.get_by_name.side_effect = lambda name: (definitions_by_name or {}).get(name)
    svc._site_engine.get_by_url.return_value = None
    return svc


class TestFaviconResolution:
    def test_definition_favicon_wins_over_guessed_favicon_ico(self):
        definition = SimpleNamespace(name="Nyaa", favicon="https://nyaa.si/static/favicon.png")
        svc = _service(
            [{"name": "Nyaa", "strict_url": "https://nyaa.si"}],
            [definition],
            {"Nyaa": definition},
        )

        assert svc._resolve("Nyaa") == ("/img/favicon/external/https%3A%2F%2Fnyaa.si%2Fstatic%2Ffavicon.png")

    def test_fallback_used_only_without_definition_favicon(self):
        definition = SimpleNamespace(name="Nyaa", favicon="")
        svc = _service(
            [{"name": "Nyaa", "strict_url": "https://nyaa.si"}],
            [definition],
            {"Nyaa": definition},
        )

        assert svc._resolve("Nyaa") == "/img/favicon/nyaa.si"

    def test_all_favicons_uses_definition_paths(self):
        definition = SimpleNamespace(name="Nyaa", favicon="https://nyaa.si/static/favicon.png")
        svc = _service(
            [{"name": "Nyaa", "strict_url": "https://nyaa.si"}],
            [definition],
            {"Nyaa": definition},
        )

        assert svc.get_all_favicons()["Nyaa"].startswith("/img/favicon/external/")
