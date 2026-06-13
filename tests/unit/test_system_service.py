"""SystemService 兼容入口单元测试."""

import app.services.system_service as system_service


def test_system_service_exports():
    assert hasattr(system_service, "SystemInfoService")
    assert hasattr(system_service, "SystemConfigService")
    assert hasattr(system_service, "MessageClientService")
    assert hasattr(system_service, "SchedulerService")
    assert hasattr(system_service, "backup")
    assert hasattr(system_service, "restart_service")
    assert hasattr(system_service, "start_service")
    assert hasattr(system_service, "stop_service")
    assert "SystemInfoService" in system_service.__all__
    assert "backup" in system_service.__all__
