"""SystemService - 系统管理业务层兼容入口.

保留与原 system_service.py 兼容的公共 API，所有实现已迁移到 app.services.system 子包。
"""

from app.services.system.backup import BackupRestoreService, backup
from app.services.system.config import (
    ConfigUpdateService,
    IndexerConfigService,
    MediaServerConfigService,
    SystemConfigService,
)
from app.services.system.info import (
    NetTestService,
    ProgressService,
    SystemInfoService,
    UserManageService,
    VersionService,
    WebSearchService,
    get_commands,
    get_rmt_modes,
    parse_brush_rule_string,
)
from app.services.system.lifecycle import (
    SchedulerService,
    SystemLifecycleService,
    restart_server,
    restart_service,
    start_service,
    stop_service,
)
from app.services.system.message import (
    MessageClientService,
    MessageCommandHandler,
    MessageSenderService,
)

__all__ = [
    "BackupRestoreService",
    "ConfigUpdateService",
    "IndexerConfigService",
    "MediaServerConfigService",
    "MessageClientService",
    "MessageCommandHandler",
    "MessageSenderService",
    "NetTestService",
    "ProgressService",
    "SchedulerService",
    "SystemConfigService",
    "SystemInfoService",
    "SystemLifecycleService",
    "UserManageService",
    "VersionService",
    "WebSearchService",
    "backup",
    "get_commands",
    "get_rmt_modes",
    "parse_brush_rule_string",
    "restart_server",
    "restart_service",
    "start_service",
    "stop_service",
]
