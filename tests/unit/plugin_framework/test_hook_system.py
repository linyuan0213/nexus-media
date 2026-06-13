"""HookSystem 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.plugin_framework.hook_system import HookSystem


class _HookRecord:
    EVENT = "download.completed"
    PLUGIN_ID = "plugin1"


class _HookRecord2:
    EVENT = "download.failed"
    PLUGIN_ID = "plugin2"


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_all_hooks.return_value = []
    return repo


@pytest.fixture
def system(mock_repo):
    return HookSystem(repo=mock_repo)


class TestHookSystem:
    def test_load_from_db(self, mock_repo):
        mock_repo.get_all_hooks.return_value = [_HookRecord(), _HookRecord2()]
        hs = HookSystem(repo=mock_repo)
        assert "download.completed" in hs.EVENTS
        assert "download.failed" in hs.EVENTS

    def test_load_from_db_exception(self, mock_repo):
        mock_repo.get_all_hooks.side_effect = Exception("db error")
        hs = HookSystem(repo=mock_repo)
        assert hs.EVENTS == []

    def test_register(self, system, mock_repo):
        system.register("download.completed", "plugin1")
        assert "download.completed" in system.EVENTS
        mock_repo.insert_hook.assert_called_once_with("plugin1", "download.completed")

    def test_register_duplicate(self, system, mock_repo):
        system.register("download.completed", "plugin1")
        system.register("download.completed", "plugin1")
        assert len(system.list_subscriptions()) == 1

    def test_unregister(self, system, mock_repo):
        system.register("download.completed", "plugin1")
        system.unregister("download.completed", "plugin1")
        assert system.list_subscriptions() == []
        mock_repo.delete_hook.assert_called_once_with("plugin1", "download.completed")

    def test_unregister_all(self, system, mock_repo):
        system.register("e1", "p1")
        system.register("e2", "p1")
        system.register("e1", "p2")
        system.unregister_all("p1")
        subs = system.list_subscriptions()
        assert len(subs) == 1
        assert subs[0]["plugin_id"] == "p2"

    def test_emit_no_handlers(self, system):
        system.emit("missing")

    def test_emit_no_sandbox(self, system):
        system.register("e1", "p1")
        system.emit("e1")

    def test_emit_with_sandbox(self, system):
        sandbox = MagicMock()
        system.set_plugin_sandbox(sandbox)
        system.register("e1", "p1")
        system.emit("e1", {"key": "value"})
        sandbox.call_hook.assert_called_once_with("p1", "e1", {"key": "value"})

    def test_emit_sandbox_exception(self, system):
        sandbox = MagicMock()
        sandbox.call_hook.side_effect = Exception("hook error")
        system.set_plugin_sandbox(sandbox)
        system.register("e1", "p1")
        system.emit("e1")
        sandbox.call_hook.assert_called_once()

    def test_list_subscriptions_filter(self, system):
        system.register("e1", "p1")
        system.register("e2", "p2")
        assert len(system.list_subscriptions(plugin_id="p1")) == 1
        assert system.list_subscriptions(plugin_id="p1")[0]["event"] == "e1"
