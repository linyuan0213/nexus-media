"""DI Container — 基于 dependency-injector 的声明式容器.

使用 DeclarativeContainer + _lazy 工厂函数避免循环导入。
所有 provider 默认使用 Singleton（单例）。

注册在模块加载时不执行导入，只有显式调用 provider 时才触发字符串导入。

测试覆盖:
    from dependency_injector import providers
    from app.di import container
    container.scheduler_core.override(providers.Singleton(lambda: mock_scheduler))
    container.scheduler_core.reset_override()
"""

from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from dependency_injector import containers, providers

T_co = TypeVar("T_co", covariant=True)


class Provider(Protocol[T_co]):
    """带类型参数的 provider 协议 — 用于 IDE 类型推断."""

    def __call__(self) -> T_co: ...
    def override(self, provider: Any) -> Any: ...
    def reset_override(self) -> None: ...
    def reset(self) -> Any: ...


def _lazy(module_path: str):
    """延迟加载工厂 — 避免 DeclarativeContainer 类定义时的循环导入."""

    def factory():
        module, name = module_path.rsplit(".", 1)
        cls = getattr(__import__(module, fromlist=[name]), name)
        return cls()

    return factory


def _s(module_path: str) -> Provider[Any]:
    """快捷注册 — 等效于 providers.Singleton(_lazy(module_path))."""
    return providers.Singleton(_lazy(module_path))


class Container(containers.DeclarativeContainer):
    """应用级 DI 容器 — 声明式 provider 注册."""

    # --- Core & Config ---
    system_config: Provider["SystemConfig"] = _s("app.core.system_config.SystemConfig")

    # --- Agent & AI ---
    agent_service: Provider["AgentService"] = _s("app.agent.service.AgentService")
    search_intent_agent: Provider["SearchIntentAgent"] = _s("app.agent.agents.search_intent.SearchIntentAgent")
    media_recognizer: Provider[Any] = _s("app.agent.agents.media_recognizer.MediaRecognizer")

    # --- Helpers ---
    thread_executor: Provider["ThreadExecutor"] = _s("app.infrastructure.thread.ThreadExecutor")
    progress_helper: Provider["ProgressTracker"] = _s("app.infrastructure.progress.ProgressTracker")
    words_service: Provider["WordsService"] = _s("app.services.words_service.WordsService")
    rss_helper: Provider["RssHelper"] = _s("app.services.rss_processor.RssHelper")
    drissionpage_helper: Provider["ChromeClient"] = _s("app.infrastructure.chrome.ChromeClient")
    indexer_helper: Provider["IndexerHelper"] = _s("app.indexer.configuration.IndexerHelper")

    # --- Media & Metadata ---
    media_service: Provider["MediaService"] = _s("app.media.service.MediaService")
    douban: Provider["DouBan"] = _s("app.media.external.douban.DouBan")
    douban_api: Provider[Any] = _s("app.infrastructure.external.doubanapi.apiv2.DoubanApi")
    bangumi: Provider["Bangumi"] = _s("app.media.external.bangumi.Bangumi")
    media_cache: Provider[Any] = _s("app.media.cache.media_cache.MediaCache")
    category: Provider["Category"] = _s("app.media.category.Category")
    scraper: Provider["Scraper"] = _s("app.media.scraper.Scraper")
    tmdb_lookup: Provider["TmdbLookup"] = _s("app.media.lookup.tmdb_lookup.TmdbLookup")
    tmdb_client: Provider["TmdbClient"] = _s("app.media.lookup.tmdb_client.TmdbClient")
    llm_parser: Provider["LLMParser"] = _s("app.media.parser.llm.LLMParser")
    fanart: Provider["Fanart"] = _s("app.media.fanart.Fanart")
    customization_matcher: Provider[Any] = _s("app.media.parser._customization.CustomizationMatcher")

    # --- Message & Plugin Framework ---
    message: Provider["Message"] = _s("app.message.message.Message")
    message_center: Provider["MessageCenter"] = _s("app.message.message_center.MessageCenter")
    plugin_registry: Provider["PluginRegistry"] = _s("app.plugin_framework.registry.PluginRegistry")
    hook_system: Provider["HookSystem"] = _s("app.plugin_framework.hook_system.HookSystem")
    plugin_sandbox: Provider["PluginSandbox"] = _s("app.plugin_framework.sandbox.PluginSandbox")

    # --- Sites & Indexer ---
    site_cache: Provider["SiteCache"] = _s("app.sites.site_cache.SiteCache")
    site_resolver: Provider["SiteResolver"] = _s("app.sites.site_resolver.SiteResolver")
    site_favicon_service: Provider["SiteFaviconService"] = _s("app.sites.site_favicon_service.SiteFaviconService")
    site_userinfo: Provider["SiteUserInfo"] = _s("app.sites.site_userinfo.SiteUserInfo")
    site_conf: Provider["SiteConf"] = _s("app.sites.siteconf.SiteConf")
    site_repository: Provider["SiteRepository"] = _s("app.db.repositories.site_repository.SiteRepository")
    indexer: Provider["Indexer"] = _s("app.indexer.indexer.Indexer")
    indexer_service: Provider["IndexerService"] = _s("app.services.indexer_service.IndexerService")
    search_pipeline: Provider["SearchPipeline"] = _s("app.indexer.core.pipeline.SearchPipeline")
    indexer_filter_engine: Provider["IndexerFilterEngine"] = _s("app.indexer.core.filter_engine.IndexerFilterEngine")

    # --- Scheduler & System ---
    scheduler_core: Provider["SchedulerCore"] = _s("app.services.scheduler.core.SchedulerCore")
    scheduler_service: Provider["SchedulerService"] = _s("app.services.scheduler_service.SchedulerService")
    system_lifecycle_service: Provider["SystemLifecycleService"] = _s(
        "app.services.system_service.SystemLifecycleService"
    )
    config_service: Provider["ConfigService"] = _s("app.services.config_service.ConfigService")

    # --- Business Services ---
    download_service: Provider["DownloadService"] = _s("app.services.download_service.DownloadService")
    downloader_core: Provider["DownloaderCore"] = _s("app.services.downloader_core.DownloaderCore")
    filter_service: Provider["FilterService"] = _s("app.services.filter_service.FilterService")
    media_config_service: Provider["MediaConfigService"] = _s("app.services.media_config_service.MediaConfigService")
    media_info_service: Provider["MediaInfoService"] = _s("app.services.media_info_service.MediaInfoService")
    media_library_service: Provider["MediaLibraryService"] = _s(
        "app.services.media_library_service.MediaLibraryService"
    )
    media_recommendation_service: Provider["MediaRecommendationService"] = _s(
        "app.services.media_recommendation_service.MediaRecommendationService"
    )
    media_file_service: Provider[Any] = _s("app.services.media_service.MediaFileService")
    search_result_service: Provider[Any] = _s("app.services.media_service.SearchResultService")
    transfer_history_service: Provider[Any] = _s("app.services.media_service.TransferHistoryService")
    plugin_framework_service: Provider["PluginFrameworkService"] = _s(
        "app.services.plugin_framework_service.PluginFrameworkService"
    )
    rss_task_service: Provider["RssTaskService"] = _s("app.services.rss_automation.task_service.RssTaskService")
    subscribe_history_service: Provider["SubscribeHistoryService"] = _s(
        "app.services.subscribe.management.history_service.SubscribeHistoryService"
    )
    subscribe_calendar_service: Provider["SubscribeCalendarService"] = _s(
        "app.services.subscribe.management.calendar_service.SubscribeCalendarService"
    )
    subscription_monitor: Provider["SubscriptionMonitor"] = _s("app.services.subscribe.monitor.SubscriptionMonitor")
    searcher: Provider["Searcher"] = _s("app.services.search_service.Searcher")
    site_service: Provider["SiteService"] = _s("app.services.site_service.SiteService")
    subscribe_service: Provider["SubscribeService"] = _s("app.services.subscribe_service.SubscribeService")
    sync_engine: Provider["SyncEngine"] = _s("app.services.sync_engine.SyncEngine")
    sync_service: Provider["SyncService"] = _s("app.services.sync_service.SyncService")
    transfer_engine: Provider["TransferEngine"] = _s("app.services.transfer_engine.TransferEngine")
    transfer_pipeline: Provider["TransferPipeline"] = _s("app.services.transfer_pipeline.TransferPipeline")
    filetransfer_service: Provider["FileTransferService"] = _s(
        "app.services.transfer.filetransfer_service.FileTransferService"
    )
    torrentremover_service: Provider["TorrentRemoverService"] = _s(
        "app.services.torrentremover_core.TorrentRemoverService"
    )
    tmdb_blacklist_service: Provider["TmdbBlacklistService"] = _s(
        "app.services.tmdb_blacklist_service.TmdbBlacklistService"
    )
    user_rss_service: Provider["UserRssService"] = _s("app.services.rss_automation.userrss_service.UserRssService")
    words_service: Provider["WordsService"] = _s("app.services.words_service.WordsService")
    storage_backend_service: Provider["StorageBackendService"] = _s(
        "app.services.storage_backend_service.StorageBackendService"
    )
    brush_service: Provider["BrushService"] = _s("app.services.brush_service.BrushService")
    brush_task_service: Provider["BrushTaskService"] = _s("app.services.brush_core.BrushTaskService")
    file_index_service: Provider[Any] = _s("app.services.file_index_service.FileIndexService")
    apikey_service: Provider["APIKeyService"] = _s("app.services.apikey_service.APIKeyService")
    auth_service: Provider["AuthService"] = _s("app.services.auth_service.AuthService")
    rbac_service: Provider["RBACService"] = _s("app.services.rbac_service.RBACService")
    media_server: Provider["MediaServer"] = _s("app.mediaserver.media_server.MediaServer")

    # --- System Admin Services ---
    message_client_service: Provider[Any] = _s("app.services.system_service.MessageClientService")
    message_sender_service: Provider[Any] = _s("app.services.system_service.MessageSenderService")
    net_test_service: Provider[Any] = _s("app.services.system_service.NetTestService")
    progress_service: Provider[Any] = _s("app.services.system_service.ProgressService")
    system_config_service: Provider[Any] = _s("app.services.system_service.SystemConfigService")
    system_info_service: Provider[Any] = _s("app.services.system_service.SystemInfoService")
    version_service: Provider[Any] = _s("app.services.system_service.VersionService")
    web_search_service: Provider[Any] = _s("app.services.system_service.WebSearchService")
    backup_restore_service: Provider[Any] = _s("app.services.system_service.BackupRestoreService")
    config_update_service: Provider[Any] = _s("app.services.system_service.ConfigUpdateService")
    indexer_config_service: Provider[Any] = _s("app.services.system_service.IndexerConfigService")
    media_server_config_service: Provider[Any] = _s("app.services.system_service.MediaServerConfigService")
    user_manage_service: Provider[Any] = _s("app.services.system_service.UserManageService")

    # --- Repositories ---
    storage_backend_repo: Provider["StorageBackendRepositoryAdapter"] = _s(
        "app.db.repositories.storage_backend_repo_adapter.StorageBackendRepositoryAdapter"
    )
    media_sync_repo: Provider["MediaSyncRepositoryAdapter"] = _s(
        "app.db.repositories.media_sync_repo_adapter.MediaSyncRepositoryAdapter"
    )
    media_server_repo: Provider["MediaServerRepositoryAdapter"] = _s(
        "app.db.repositories.config_repo_adapter.MediaServerRepositoryAdapter"
    )
    tmdb_blacklist_repo: Provider["TmdbBlacklistRepositoryAdapter"] = _s(
        "app.db.repositories.plugin_repo_adapter.TmdbBlacklistRepositoryAdapter"
    )
    apikey_repo: Provider[Any] = _s("app.db.repositories.apikey_repo_adapter.APIKeyRepositoryAdapter")
    apikey_log_repo: Provider[Any] = _s("app.db.repositories.apikey_repo_adapter.APIKeyLogRepositoryAdapter")
    download_history_repo: Provider["DownloadHistoryRepositoryAdapter"] = _s(
        "app.db.repositories.download_repo_adapter.DownloadHistoryRepositoryAdapter"
    )
    downloader_repo: Provider["DownloaderRepositoryAdapter"] = _s(
        "app.db.repositories.config_repo_adapter.DownloaderRepositoryAdapter"
    )
    indexer_statistics_repo: Provider["IndexerStatisticsRepositoryAdapter"] = _s(
        "app.db.repositories.download_repo_adapter.IndexerStatisticsRepositoryAdapter"
    )
    sync_path_repo: Provider["SyncPathRepositoryAdapter"] = _s(
        "app.db.repositories.sync_repo_adapter.SyncPathRepositoryAdapter"
    )
    search_repo: Provider[Any] = _s("app.db.repositories.search_repo_adapter.SearchRepositoryAdapter")
    brush_rule_repo: Provider[Any] = _s("app.db.repositories.brush_repo_adapter.BrushRuleRepositoryAdapter")
    rbac_permission_repo: Provider["RBACPermissionRepositoryAdapter"] = _s(
        "app.db.repositories.rbac_repo_adapter.RBACPermissionRepositoryAdapter"
    )
    rbac_menu_repo: Provider["RBACMenuRepositoryAdapter"] = _s(
        "app.db.repositories.rbac_repo_adapter.RBACMenuRepositoryAdapter"
    )
    rbac_role_repo: Provider["RBACRoleRepositoryAdapter"] = _s(
        "app.db.repositories.rbac_repo_adapter.RBACRoleRepositoryAdapter"
    )
    rbac_user_repo: Provider["RBACUserRepositoryAdapter"] = _s(
        "app.db.repositories.rbac_repo_adapter.RBACUserRepositoryAdapter"
    )
    rss_torrent_repo: Provider["SubscribeTorrentRepositoryAdapter"] = _s(
        "app.db.repositories.subscribe_torrent_repo_adapter.SubscribeTorrentRepositoryAdapter"
    )
    custom_word_repo: Provider["CustomWordRepositoryAdapter"] = _s(
        "app.db.repositories.word_repo_adapter.CustomWordRepositoryAdapter"
    )
    custom_word_group_repo: Provider["CustomWordGroupRepositoryAdapter"] = _s(
        "app.db.repositories.word_repo_adapter.CustomWordGroupRepositoryAdapter"
    )
    plugin_framework_repo: Provider[Any] = _s(
        "app.db.repositories.plugin_framework_repository.PluginFrameworkRepository"
    )
    torrent_remove_task_repo: Provider["TorrentRemoveTaskRepositoryAdapter"] = _s(
        "app.db.repositories.config_repo_adapter.TorrentRemoveTaskRepositoryAdapter"
    )
    download_repo: Provider["DownloadRepository"] = _s("app.db.repositories.download_repository.DownloadRepository")
    filter_group_repo: Provider["FilterGroupRepositoryAdapter"] = _s(
        "app.db.repositories.config_repo_adapter.FilterGroupRepositoryAdapter"
    )
    filter_rule_repo: Provider["FilterRuleRepositoryAdapter"] = _s(
        "app.db.repositories.config_repo_adapter.FilterRuleRepositoryAdapter"
    )
    site_repo_adapter: Provider["SiteRepositoryAdapter"] = _s(
        "app.db.repositories.site_repo_adapter.SiteRepositoryAdapter"
    )
    plugin_log_repo: Provider["PluginLogRepositoryAdapter"] = _s(
        "app.db.repositories.plugin_framework_repo_adapter.PluginLogRepositoryAdapter"
    )

    # --- Downloader Infrastructure ---
    download_client_factory: Provider["DownloadClientFactory"] = _s(
        "app.downloader.client_factory.DownloadClientFactory"
    )
    download_monitor: Provider[Any] = _s("app.services.download_monitor.DownloadMonitor")

    # --- Cache Warmers ---
    config_reloader: Provider[Any] = _s("app.services.config_reloader.ConfigReloader")
    config_cache_warmer: Provider["ConfigCacheWarmer"] = _s("app.infrastructure.cache_system.warmer.ConfigCacheWarmer")
    site_cache_warmer: Provider["SiteCacheWarmer"] = _s("app.infrastructure.cache_system.warmer.SiteCacheWarmer")
    words_cache_warmer: Provider["WordsCacheWarmer"] = _s("app.infrastructure.cache_system.warmer.WordsCacheWarmer")
    tmdb_trending_warmer: Provider["TMDBTrendingWarmer"] = _s(
        "app.infrastructure.cache_system.warmer.TMDBTrendingWarmer"
    )

    # --- HTTP Clients ---
    http_client: Provider["HttpClient"] = _s("app.infrastructure.http.client.HttpClient")
    async_http_client: Provider["AsyncHttpClient"] = _s("app.infrastructure.http.async_client.AsyncHttpClient")

    # --- Event Bus ---
    event_bus: Provider["EventBus"] = _s("app.events.factory.create_event_bus")
    rate_limit_engine: Provider["RateLimitEngine"] = _s("app.infrastructure.rate_limiter.RateLimitEngine")


# 全局容器实例
container = Container()

if TYPE_CHECKING:
    from app.agent.agents.search_intent import SearchIntentAgent
    from app.agent.service import AgentService
    from app.core.system_config import SystemConfig
    from app.db.repositories.config_repo_adapter import (
        DownloaderRepositoryAdapter,
        FilterGroupRepositoryAdapter,
        FilterRuleRepositoryAdapter,
        MediaServerRepositoryAdapter,
        TorrentRemoveTaskRepositoryAdapter,
    )
    from app.db.repositories.download_repo_adapter import (
        DownloadHistoryRepositoryAdapter,
        IndexerStatisticsRepositoryAdapter,
    )
    from app.db.repositories.download_repository import DownloadRepository
    from app.db.repositories.media_sync_repo_adapter import MediaSyncRepositoryAdapter
    from app.db.repositories.plugin_framework_repo_adapter import PluginLogRepositoryAdapter
    from app.db.repositories.plugin_repo_adapter import TmdbBlacklistRepositoryAdapter
    from app.db.repositories.rbac_repo_adapter import (
        RBACMenuRepositoryAdapter,
        RBACPermissionRepositoryAdapter,
        RBACRoleRepositoryAdapter,
        RBACUserRepositoryAdapter,
    )
    from app.db.repositories.subscribe_torrent_repo_adapter import SubscribeTorrentRepositoryAdapter
    from app.db.repositories.site_repo_adapter import SiteRepositoryAdapter
    from app.db.repositories.site_repository import SiteRepository
    from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
    from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
    from app.db.repositories.word_repo_adapter import (
        CustomWordGroupRepositoryAdapter,
        CustomWordRepositoryAdapter,
    )
    from app.downloader.client_factory import DownloadClientFactory
    from app.events.bus import EventBus
    from app.infrastructure.http.async_client import AsyncHttpClient
    from app.infrastructure.http.client import HttpClient
    from app.infrastructure.rate_limiter import RateLimitEngine
    from app.infrastructure.chrome import ChromeClient
    from app.indexer.configuration import IndexerHelper
    from app.infrastructure.progress import ProgressTracker
    from app.services.rss_processor import RssHelper
    from app.infrastructure.thread import ThreadExecutor
    from app.services.words_service import WordsService
    from app.indexer.core.filter_engine import IndexerFilterEngine
    from app.indexer.core.pipeline import SearchPipeline
    from app.indexer.indexer import Indexer
    from app.infrastructure.cache_system.warmer import (
        ConfigCacheWarmer,
        SiteCacheWarmer,
        TMDBTrendingWarmer,
        WordsCacheWarmer,
    )
    from app.media.category import Category
    from app.media.external.bangumi import Bangumi
    from app.media.external.douban import DouBan
    from app.media.fanart import Fanart
    from app.media.lookup.tmdb_client import TmdbClient
    from app.media.lookup.tmdb_lookup import TmdbLookup
    from app.media.parser.llm import LLMParser
    from app.media.scraper import Scraper
    from app.media.service import MediaService
    from app.mediaserver.media_server import MediaServer
    from app.message.message import Message
    from app.message.message_center import MessageCenter
    from app.plugin_framework.hook_system import HookSystem
    from app.plugin_framework.registry import PluginRegistry
    from app.plugin_framework.sandbox import PluginSandbox
    from app.services.apikey_service import APIKeyService
    from app.services.auth_service import AuthService
    from app.services.brush_core import BrushTaskService
    from app.services.brush_service import BrushService
    from app.services.config_service import ConfigService
    from app.services.download_service import DownloadService
    from app.services.downloader_core import DownloaderCore
    from app.services.filter_service import FilterService
    from app.services.indexer_service import IndexerService
    from app.services.media_config_service import MediaConfigService
    from app.services.media_info_service import MediaInfoService
    from app.services.media_library_service import MediaLibraryService
    from app.services.media_recommendation_service import MediaRecommendationService
    from app.services.plugin_framework_service import PluginFrameworkService
    from app.services.rbac_service import RBACService
    from app.services.rss_automation.task_service import RssTaskService
    from app.services.subscribe.management.calendar_service import SubscribeCalendarService
    from app.services.subscribe.management.history_service import SubscribeHistoryService
    from app.services.subscribe.monitor import SubscriptionMonitor
    from app.services.scheduler.core import SchedulerCore
    from app.services.scheduler_service import SchedulerService
    from app.services.search_service import Searcher
    from app.services.site_service import SiteService
    from app.services.storage_backend_service import StorageBackendService
    from app.services.subscribe_service import SubscribeService
    from app.services.sync_engine import SyncEngine
    from app.services.sync_service import SyncService
    from app.services.system_service import SystemLifecycleService
    from app.services.tmdb_blacklist_service import TmdbBlacklistService
    from app.services.torrentremover_core import TorrentRemoverService
    from app.services.transfer.filetransfer_service import FileTransferService
    from app.services.transfer_engine import TransferEngine
    from app.services.transfer_pipeline import TransferPipeline
    from app.services.rss_automation.userrss_service import UserRssService
    from app.sites.site_cache import SiteCache
    from app.sites.site_favicon_service import SiteFaviconService
    from app.sites.site_resolver import SiteResolver
    from app.sites.site_userinfo import SiteUserInfo
    from app.sites.siteconf import SiteConf
