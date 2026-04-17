"""
Tests to verify that the WebAction refactor preserves all public actions/commands.
"""
import ast
import os
from contextlib import ExitStack
from pathlib import Path

import pytest
from flask import Flask
from unittest.mock import MagicMock, patch

os.environ.setdefault("NASTOOL_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))

# Heavy dependencies that may hit DB/network during controller import
_HEAVY_PATCHES = [
    "app.torrentremover.TorrentRemover",
    "app.downloader.Downloader",
    "app.sync.Sync",
    "app.rss.Rss",
    "app.subscribe.Subscribe",
    "app.brushtask.BrushTask",
    "app.rsschecker.RssChecker",
    "app.message.Message",
    "app.media.Media",
    "app.media.category.Category",
]


def _make_test_app():
    app = Flask(__name__)
    app.secret_key = "test"
    patches = [patch(target, new=MagicMock()) for target in _HEAVY_PATCHES]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from web.controllers import register_blueprints
        register_blueprints(app)
    return app


@pytest.fixture(scope="module")
def app():
    return _make_test_app()


class TestWebActionRefactor:
    def test_blueprint_routes_count(self, app):
        route_count = len([r for r in app.url_map.iter_rules() if "api/web" in str(r)])
        assert route_count >= 198, f"expected >= 198 blueprint routes, got {route_count}"

    def test_key_routes_exist(self, app):
        urls = {str(r) for r in app.url_map.iter_rules()}
        for expected in [
            "/api/web/system/restart",
            "/api/web/media/search_media_infos",
            "/api/web/download/get_downloading",
            "/api/web/scheduler/get_scheduler_jobs",
            "/api/web/rbac/get_users",
        ]:
            assert expected in urls, f"missing route {expected}"

    def test_static_methods_accessible(self):
        from web.action import WebAction
        assert hasattr(WebAction, "mediainfo_dict")
        assert hasattr(WebAction, "delete_media_file")
        assert hasattr(WebAction, "get_media_exists_info")

    def test_actions_directory_removed(self):
        base = Path(__file__).parent.parent / "web" / "actions"
        assert not base.exists(), "web/actions/ directory should be removed"

    def test_syntax_valid(self):
        for p in (Path(__file__).parent.parent / "web" / "controllers").glob("*.py"):
            if p.name == "__init__.py":
                continue
            ast.parse(p.read_text(encoding="utf-8"))

    def test_apiv1_syntax_valid(self):
        p = Path(__file__).parent.parent / "web" / "apiv1.py"
        ast.parse(p.read_text(encoding="utf-8"))

    def test_util_js_has_ajax_post(self):
        util_js = Path(__file__).parent.parent / "web" / "static" / "js" / "util.js"
        content = util_js.read_text(encoding="utf-8")
        assert "ajax_post" in content, "util.js should contain ajax_post"
        assert "CMD_URL_MAP" not in content, "util.js should no longer contain CMD_URL_MAP"
