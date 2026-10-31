"""插件依赖检测测试."""

from app.plugin_framework.dependency_manager import PluginDependencyManager


def test_check_dependency_uses_distribution_name_for_import_mismatch():
    assert PluginDependencyManager.check_dependency("pillow") is True


def test_check_dependency_handles_version_specifier():
    assert PluginDependencyManager.check_dependency("requests>=2") is True


def test_check_dependency_returns_false_for_missing_package():
    assert PluginDependencyManager.check_dependency("definitely-missing-pkg-xyz") is False
