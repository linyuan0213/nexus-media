from unittest.mock import MagicMock

from app.plugin_framework.builtin_plugins.autogenrss.backend.generator import (
    RssGenEngine,
)
from app.plugin_framework.builtin_plugins.autogenrss.backend.handlers.base import (
    SiteRssGenResult,
)


class TestRssGenEngine:
    def _make_engine(self, registry=None, site_cache=None):
        ctx = MagicMock()
        ctx.info = MagicMock()
        ctx.debug = MagicMock()
        ctx.warn = MagicMock()
        ctx.error = MagicMock()
        ctx.notify = MagicMock()
        registry = registry or MagicMock()
        if site_cache is None:
            site_cache = MagicMock()
            site_cache.get_sites.return_value = []
        return RssGenEngine(ctx, registry, site_cache=site_cache)

    def test_no_sites(self):
        engine = self._make_engine()
        engine.run({"rss_sites": []})
        engine.ctx.info.assert_called_with("没有需要生成的站点，停止运行")

    def test_success_and_failure(self):
        registry = MagicMock()
        site_cache = MagicMock()
        site_cache.get_sites.return_value = [
            {"id": "1", "name": "site1"},
            {"id": "2", "name": "site2"},
        ]

        def _make_handler(ok):
            handler = MagicMock()
            handler.generate.return_value = SiteRssGenResult.custom(ok, f"site_{ok}")
            return handler

        registry.get.side_effect = [lambda: _make_handler(True), lambda: _make_handler(False)]
        registry.get_fallback.return_value = None
        registry.get_generic.return_value = lambda: _make_handler(False)

        engine = self._make_engine(registry=registry, site_cache=site_cache)
        engine.run({"rss_sites": ["1", "2"], "notify": True})

        assert engine.ctx.info.call_args_list[-1][0][0] == "生成RSS任务完成！"
        engine.ctx.notify.assert_called_once()

    def test_handler_exception(self):
        registry = MagicMock()
        site_cache = MagicMock()
        site_cache.get_sites.return_value = [{"id": "1", "name": "site1"}]

        handler = MagicMock()
        handler.generate.side_effect = Exception("boom")
        registry.get.return_value = lambda: handler

        engine = self._make_engine(registry=registry, site_cache=site_cache)
        engine.run({"rss_sites": ["1"]})

        engine.ctx.warn.assert_called_once()
