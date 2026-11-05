"""插件后台启用线程与生命周期锁的回归测试."""

from contextlib import contextmanager

from app.core.exceptions import PluginInstallingError
from app.services.plugin_framework_service import PluginFrameworkService


def test_do_enable_does_not_raise_when_lifecycle_lock_is_held():
    service = PluginFrameworkService.__new__(PluginFrameworkService)

    @contextmanager
    def blocked(_plugin_id):
        raise PluginInstallingError("busy")
        yield

    service._lifecycle_guard = blocked  # type: ignore[method-assign]
    service._do_enable("private_metadata")
