"""
Tests to verify that the WebAction refactor preserves all public actions/commands.
"""
import os
import sys
import importlib
from contextlib import ExitStack
import pytest
from unittest.mock import MagicMock, patch

# Ensure config is available before importing WebAction
os.environ.setdefault("NASTOOL_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))


# Monkey-patch heavy singletons that hit the DB/network so that instantiating
# WebAction (which builds _commands) stays lightweight and testable.
_HeavyClasses = [
    "app.torrentremover.TorrentRemover",
    "app.downloader.Downloader",
    "app.sync.Sync",
    "app.rss.Rss",
    "app.subscribe.Subscribe",
    "app.brushtask.BrushTask",
    "app.rsschecker.RssChecker",
    "app.message.Message",
]


def _make_webaction():
    # Evict cached submodules so patches take effect on a fresh import
    for mod in list(sys.modules):
        if mod.startswith("web.") or mod.startswith("app."):
            sys.modules.pop(mod, None)
    # Replace the class itself with a MagicMock so calls like TorrentRemover()
    # return a mock without triggering real __init__.
    patches = [patch(target, new=MagicMock()) for target in _HeavyClasses]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        import web.action
        importlib.reload(web.action)
        from web.action import WebAction as WA
        return WA()


@pytest.fixture(scope="module")
def webaction():
    return _make_webaction()


class TestWebActionEntryPoints:
    def test_actions_populated(self, webaction):
        assert len(webaction._actions) == 198
        # spot-check some domain actions
        for key in ["sch", "search", "download", "pt_start", "update_site",
                    "get_site", "add_rss_media", "get_users", "get_plugin_apps",
                    "get_scheduler_jobs", "update_scheduler_job", "delete_scheduler_job",
                    "pause_scheduler_job", "resume_scheduler_job", "run_scheduler_job"]:
            assert key in webaction._actions, f"missing action {key}"

    def test_commands_populated(self, webaction):
        assert len(webaction._commands) == 10
        for key in ["/ptr", "/ptt", "/rss", "/tbl", "/trh"]:
            assert key in webaction._commands, f"missing command {key}"

    def test_api_action_wraps(self, webaction):
        # api_action should wrap action results into a uniform envelope
        result = webaction.api_action("sch", {"item": "sync"})
        assert "code" in result
        assert "success" in result
        assert "message" in result
        assert "data" in result

    def test_static_methods_accessible(self, webaction):
        from web.action import WebAction
        # mediainfo_dict is defined in base mixin
        assert hasattr(WebAction, "mediainfo_dict")
        # delete_media_file is a staticmethod in base mixin
        assert hasattr(WebAction, "delete_media_file")
        # get_media_exists_info is a staticmethod in media mixin
        assert hasattr(WebAction, "get_media_exists_info")

    def test_action_file_structure(self):
        from pathlib import Path
        base = Path(__file__).parent.parent / "web" / "actions"
        expected = {
            "_base.py", "_system.py", "_media.py", "_site.py",
            "_download.py", "_rss.py", "_userrss.py", "_filter.py",
            "_words.py", "_brush.py", "_sync.py", "_plugin.py", "_rbac.py",
            "_scheduler.py", "__init__.py",
        }
        assert set(p.name for p in base.glob("*.py")) == expected

    def test_syntax_valid(self):
        import ast
        from pathlib import Path
        for p in (Path(__file__).parent.parent / "web" / "actions").glob("*.py"):
            if p.name == "__init__.py":
                continue
            ast.parse(p.read_text(encoding="utf-8"))
