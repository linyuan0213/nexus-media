"""工具执行上下文 — 类型化依赖注入（替代旧 deps dict）"""

from dataclasses import dataclass
from typing import Any

from app.schemas.auth import UserContext


@dataclass(frozen=True)
class ToolContext:
    """工具执行上下文 — 仅含 MVP 工具所需的最小服务集合"""

    search_orchestrator: Any
    searcher: Any
    download_service: Any
    downloader_core: Any
    subscribe_service: Any
    media_service: Any
    media_info_service: Any
    filetransfer_service: Any
    scheduler_service: Any
    system_info_service: Any
    event_bus: Any
    site_service: Any = None
    brush_service: Any = None
    media_library_service: Any = None
    transfer_history_service: Any = None
    user_rss_service: Any = None
    knowledge_ingestor: Any = None
    indexer_service: Any = None
    torrent_remover_service: Any = None
    storage_backend_service: Any = None
    words_service: Any = None
    plugin_framework_service: Any = None
    message_client_service: Any = None
    media_server_config_service: Any = None
    indexer_config_service: Any = None
    system_config_service: Any = None
    media_config_service: Any = None
    sync_service: Any = None
    retriever: Any = None
    conversation_store: Any = None
    semantic_memory: Any = None
    rbac_service: Any = None
    site_grant_service: Any = None

    def user_context(self, user_id: str | int | None):
        """按调用方 user_id 构建 UserContext（含权限与角色码快照）.

        user_id 为空/0 时返回 None（系统上下文语义：不过滤）。
        """
        if not user_id or not str(user_id).isdigit() or int(user_id) == 0:
            return None
        uid = int(user_id)
        if self.rbac_service is None:
            return UserContext(user_id=uid, username=str(uid), level=0, permissions=[], role_codes=[])
        snapshot = self.rbac_service.get_user_snapshot(uid)
        user = self.rbac_service.get_user_by_id(uid)
        return UserContext(
            user_id=uid,
            username=getattr(user, "USERNAME", str(uid)) if user else str(uid),
            level=getattr(user, "LEVEL", 0) or 0 if user else 0,
            permissions=sorted(snapshot.permissions),
            role_codes=sorted(snapshot.role_codes),
        )
