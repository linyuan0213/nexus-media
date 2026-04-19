import pytest
from unittest.mock import MagicMock

from app.schemas.plugin import PluginAppsDTO, PluginPageDTO, PluginInstallResultDTO
from app.services.plugin_service import PluginService
from app.utils.types import SystemConfigKey


@pytest.fixture
def svc():
    mock_pm = MagicMock()
    mock_sc = MagicMock()
    mock_ph = MagicMock()
    return PluginService(
        plugin_manager=mock_pm,
        system_config=mock_sc,
        plugin_helper=mock_ph,
    )


class TestUpdatePluginConfig:
    def test_ok(self, svc):
        svc.update_plugin_config("p1", {"key": "val"})
        svc._pm.save_plugin_config.assert_called_once_with(pid="p1", conf={"key": "val"})
        svc._pm.reload_plugin.assert_called_once_with("p1")


class TestGetPluginApps:
    def test_ok(self, svc):
        svc._pm.get_plugin_apps.return_value = [{"id": "p1"}]
        svc._helper.statistic.return_value = {"count": 1}
        dto = svc.get_plugin_apps(1)
        assert dto.plugins == [{"id": "p1"}]
        assert dto.statistic == {"count": 1}


class TestGetPluginPage:
    def test_ok(self, svc):
        svc._pm.get_plugin_page.return_value = ("Title", "Content", None)
        dto = svc.get_plugin_page("p1")
        assert dto.title == "Title"
        assert dto.content == "Content"


class TestGetPluginState:
    def test_ok(self, svc):
        svc._pm.get_plugin_state.return_value = "RUNNING"
        assert svc.get_plugin_state("p1") == "RUNNING"


class TestGetPluginsConf:
    def test_ok(self, svc):
        svc._pm.get_plugins_conf.return_value = {"p1": {}}
        assert svc.get_plugins_conf(1) == {"p1": {}}


class TestInstallPlugin:
    def test_success(self, svc):
        svc._sys_conf.get.return_value = []
        dto = svc.install_plugin("p1")
        assert dto.success is True
        svc._pm.init_config.assert_called_once()

    def test_already_installed(self, svc):
        svc._sys_conf.get.return_value = ["p1"]
        dto = svc.install_plugin("p1")
        assert dto.success is True
        svc._pm.init_config.assert_called_once()

    def test_no_id(self, svc):
        dto = svc.install_plugin("")
        assert dto.success is False


class TestUninstallPlugin:
    def test_success(self, svc):
        svc._sys_conf.get.return_value = ["p1"]
        dto = svc.uninstall_plugin("p1")
        assert dto.success is True
        svc._pm.init_config.assert_called_once()

    def test_not_installed(self, svc):
        svc._sys_conf.get.return_value = []
        dto = svc.uninstall_plugin("p1")
        assert dto.success is True

    def test_no_id(self, svc):
        dto = svc.uninstall_plugin("")
        assert dto.success is False


class TestRunPluginMethod:
    def test_ok(self, svc):
        svc._pm.run_plugin_method.return_value = {"r": 1}
        result = svc.run_plugin_method("p1", "test", {"a": 1})
        assert result == {"r": 1}
        svc._pm.run_plugin_method.assert_called_once_with(
            pid="p1", method="test", a=1)
