"""对象工厂 — 兼容层.

已由分模块 Builder 接管对象图组装. 本文件仅保留 Registry 兼容接口,
供旧代码在迁移期间继续通过 registry.get() 获取依赖.
"""

import log

from app.di.builders.context_builder import build_app_context
from app.di.context import AppContext
from app.di.registry import registry
from app.di.types import RegistryKey
from app.services.site_config_updater import SiteConfigUpdater, update_site_config_at_startup
from app.sites.engine import SiteEngine


def _register_context_in_registry(context: AppContext) -> None:
    """将 AppContext 中的对象注册到 Registry，兼容旧代码."""
    registry.set(RegistryKey.EVENT_BUS, context.event_bus)
    registry.set(RegistryKey.THREAD_EXECUTOR, context.thread_executor)
    registry.set(RegistryKey.SCHEDULER_CORE, context.scheduler_core)
    registry.set(RegistryKey.MESSAGE, context.message)
    registry.set(RegistryKey.SITE_CACHE, context.site_cache)
    registry.set(RegistryKey.SITE_ENGINE, context.site_engine)
    registry.set(RegistryKey.HOOK_SYSTEM, context.hook_system)
    registry.set(RegistryKey.PLUGIN_SANDBOX, context.plugin_sandbox)
    registry.set(RegistryKey.MEDIA_SERVER, context.media_server)
    registry.set(RegistryKey.APIKEY_SERVICE, context.apikey_service)

    registry.set(RegistryKey.MEDIA_SERVICE, context.media_service)
    registry.set(RegistryKey.TMDB_CLIENT, context.tmdb_client)
    registry.set(RegistryKey.AGENT_SERVICE, context.agent_service)
    registry.set(RegistryKey.MEDIA_RECOGNIZER, context.media_recognizer)
    registry.set(RegistryKey.SEARCH_INTENT_AGENT, context.search_intent_agent)
    registry.set(RegistryKey.DOWNLOAD_MONITOR, context.download_monitor)

    registry.set(RegistryKey.DOWNLOADER_CORE, context.downloader_core)
    registry.set(RegistryKey.FILETRANSFER_SERVICE, context.filetransfer_service)
    registry.set(RegistryKey.SYNC_ENGINE, context.sync_engine)
    registry.set(RegistryKey.SYNC_SERVICE, context.sync_service)
    registry.set(RegistryKey.FILE_INDEX_SERVICE, context.file_index_service)
    registry.set(RegistryKey.INDEXER_SERVICE, context.indexer_service)
    registry.set(RegistryKey.SUBSCRIBE_SERVICE, context.subscribe_service)
    registry.set(RegistryKey.SEARCHER, context.searcher)
    registry.set(RegistryKey.RSS_TASK_SERVICE, context.rss_task_service)
    registry.set(RegistryKey.FILTER_SERVICE, context.filter_service)
    registry.set(RegistryKey.TORRENTREMOVER_SERVICE, context.torrent_remover_service)
    registry.set(RegistryKey.BRUSH_TASK_SERVICE, context.brush_task_service)
    registry.set(RegistryKey.BRUSH_SERVICE, context.brush_service)
    registry.set(RegistryKey.SITE_SERVICE, context.site_service)
    registry.set(RegistryKey.SITE_RESOLVER, context.site_resolver)
    registry.set(RegistryKey.SITE_FAVICON_SERVICE, context.site_favicon_service)
    registry.set(RegistryKey.MEDIA_INFO_SERVICE, context.media_info_service)
    registry.set(RegistryKey.MEDIA_CONFIG_SERVICE, context.media_config_service)
    registry.set(RegistryKey.MEDIA_FILE_SERVICE, context.media_file_service)
    registry.set(RegistryKey.MEDIA_LIBRARY_SERVICE, context.media_library_service)
    registry.set(RegistryKey.MEDIA_RECOMMENDATION_SERVICE, context.media_recommendation_service)
    registry.set(RegistryKey.MEDIA_SERVER_CONFIG_SERVICE, context.media_server_config_service)
    registry.set(RegistryKey.SYSTEM_CONFIG_SERVICE, context.system_config_service)
    registry.set(RegistryKey.INDEXER_CONFIG_SERVICE, context.indexer_config_service)
    registry.set(RegistryKey.RBAC_SERVICE, context.rbac_service)
    registry.set(RegistryKey.CONFIG_SERVICE, context.config_service)
    registry.set(RegistryKey.MESSAGE_SENDER_SERVICE, context.message_sender_service)
    registry.set(RegistryKey.MESSAGE_CLIENT_SERVICE, context.message_client_service)
    registry.set(RegistryKey.SCHEDULER_SERVICE, context.scheduler_service)
    registry.set(RegistryKey.SYSTEM_INFO_SERVICE, context.system_info_service)
    registry.set(RegistryKey.NET_TEST_SERVICE, context.net_test_service)
    registry.set(RegistryKey.PROGRESS_SERVICE, context.progress_service)
    registry.set(RegistryKey.WEB_SEARCH_SERVICE, context.web_search_service)
    registry.set(RegistryKey.BACKUP_RESTORE_SERVICE, context.backup_restore_service)
    registry.set(RegistryKey.USER_MANAGE_SERVICE, context.user_manage_service)
    registry.set(RegistryKey.TMDB_BLACKLIST_SERVICE, context.tmdb_blacklist_service)
    registry.set(RegistryKey.DOWNLOAD_SERVICE, context.download_service)
    registry.set(RegistryKey.PLUGIN_FRAMEWORK_SERVICE, context.plugin_framework_service)
    registry.set(RegistryKey.STORAGE_BACKEND_SERVICE, context.storage_backend_service)
    registry.set(RegistryKey.SEARCH_RESULT_SERVICE, context.search_result_service)
    registry.set(RegistryKey.TRANSFER_HISTORY_SERVICE, context.transfer_history_service)
    registry.set(RegistryKey.SUBSCRIBE_CALENDAR_SERVICE, context.subscribe_calendar_service)
    registry.set(RegistryKey.SUBSCRIBE_HISTORY_SERVICE, context.subscribe_history_service)
    registry.set(RegistryKey.WORDS_SERVICE, context.words_service)
    registry.set(RegistryKey.USER_RSS_SERVICE, context.user_rss_service)
    registry.set(RegistryKey.SYSTEM_LIFECYCLE, context.system_lifecycle)


def build_all() -> None:
    """按拓扑顺序创建所有对象并注册到 registry."""
    context = build_app_context()
    _register_context_in_registry(context)


def _register_post_db_services() -> None:
    """兼容旧 lifespan 调用 — 已由 Builder 在数据库初始化前构造.

    保留空实现避免 api/main.py 改动期间报错.
    """
    log.debug("[_register_post_db_services] 已由 Builder 预构造，无需额外注册")


def init_site_config() -> None:
    """初始化站点配置（需要在数据库初始化后执行）."""
    log.info("[FastAPI]初始化站点配置...")
    try:
        updater = SiteConfigUpdater()
        updater.ensure_local_sites(SiteEngine._BUILTIN_DEFINITIONS_DIR)
        update_site_config_at_startup()
    except Exception as e:
        log.warn(f"[FastAPI]站点配置初始化失败: {e!s}")
