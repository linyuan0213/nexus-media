"""对象工厂 — 按正确拓扑顺序创建所有对象。

创建顺序（依赖方向：下层 → 上层）：
Layer 0: 配置、数据库连接
Layer 1: 基础设施（EventBus, HttpClient, CacheManager...）
Layer 2: 业务组件（MessageCenter, EventHandlerRegistry...）
Layer 3: 业务 Facade（Message, MediaService...）
Layer 4: Service（SyncService, DownloadCore...）
Layer 5: 协调器（SystemLifecycleService）
"""

import log

from app import utils as string_utils_module
from app.agent.service import AgentService
from app.agent.tool_executor import ToolExecutor
from app.core.system_config import SystemConfig
from app.db.repositories.apikey_repo_adapter import APIKeyLogRepositoryAdapter, APIKeyRepositoryAdapter
from app.db.repositories.brush_repo_adapter import BrushRuleRepositoryAdapter, BrushTaskRepositoryAdapter
from app.db.repositories.config_repo_adapter import (
    DownloaderRepositoryAdapter,
    FilterGroupRepositoryAdapter,
    FilterRuleRepositoryAdapter,
    MediaConfigRepositoryAdapter,
    MediaServerRepositoryAdapter,
    TorrentRemoveTaskRepositoryAdapter,
    UserRssConfigRepositoryAdapter,
)
from app.db.repositories.download_repo_adapter import (
    DownloadHistoryRepositoryAdapter,
    DownloadSettingRepositoryAdapter,
    IndexerStatisticsRepositoryAdapter,
)
from app.db.repositories.plugin_framework_repo_adapter import PluginLogRepositoryAdapter
from app.db.repositories.plugin_framework_repository import PluginFrameworkRepository
from app.db.repositories.rbac_repo_adapter import RBACMenuRepositoryAdapter, RBACRoleRepositoryAdapter
from app.db.repositories.search_repo_adapter import SearchRepositoryAdapter
from app.db.repositories.site_repo_adapter import SiteRepositoryAdapter
from app.db.repositories.site_repository import SiteRepository
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.db.repositories.subscribe_repo_adapter import (
    SubscribeHistoryRepositoryAdapter,
    SubscribeMovieRepositoryAdapter,
    SubscribeTvEpisodeRepositoryAdapter,
    SubscribeTvRepositoryAdapter,
)
from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
from app.db.repositories.transfer_repo_adapter import TransferBlacklistRepositoryAdapter
from app.db.repositories.word_repo_adapter import CustomWordRepositoryAdapter, CustomWordGroupRepositoryAdapter
from app.di.registry import registry
from app.di.types import RegistryKey
from app.downloader.client_factory import DownloadClientFactory
from app.events.bridge import PluginBridge
from app.events.bus import EventBus
from app.events.registry import EventHandlerRegistry
from app.indexer.core.pipeline import SearchPipeline
from app.indexer.indexer import Indexer
from app.indexer.configuration import IndexerHelper
from app.infrastructure.progress.tracker import ProgressTracker
from app.infrastructure.queue.factory import MessageQueueFactory
from app.infrastructure.thread import ThreadExecutor
from app.media import MediaCache
from app.media.external.bangumi import Bangumi
from app.media.external.douban import DouBan
from app.media.lookup.tmdb_client import TmdbClient
from app.media.lookup.tmdb_lookup import TmdbLookup
from app.media.parser._release_groups import ReleaseGroupsMatcher
from app.media.parser.llm import LLMParser
from app.media.scraper import Scraper
from app.media.service import MediaService
from app.mediaserver.media_server import MediaServer
from app.message.message import Message
from app.plugin_framework.hook_system import HookSystem
from app.plugin_framework.registry import PluginRegistry
from app.plugin_framework.sandbox import PluginSandbox
from app.services.apikey_service import APIKeyService
from app.services.brush.scheduler import BrushTaskScheduler
from app.services.brush.task_service import BrushTaskService
from app.services.brush_service import BrushService
from app.services.config_service import ConfigService
from app.services.download_core import DownloadCore
from app.services.download_monitor import DownloadMonitor
from app.services.downloader_core import DownloaderCore
from app.services.download_service import DownloadService
from app.services.file_index_service import FileIndexService
from app.services.filter_service import FilterService
from app.services.indexer_service import IndexerService
from app.services.media_config_service import MediaConfigService
from app.services.media_file_service import MediaFileService
from app.services.media_info_service import MediaInfoService
from app.services.media_library_service import MediaLibraryService
from app.services.media_recommendation_service import MediaRecommendationService
from app.services.plugin_framework_service import PluginFrameworkService
from app.services.rbac.service import RBACService
from app.services.rss_automation.task_service import RssTaskService
from app.services.rss_automation.userrss_service import UserRssService
from app.services.rss_processor import RssHelper
from app.services.scheduler.core import SchedulerCore
from app.services.scheduler_service import SchedulerService
from app.services.search_result_service import SearchResultService
from app.services.search_service import Searcher
from app.services.site_config_updater import SiteConfigUpdater, update_site_config_at_startup
from app.services.site_service import SiteService
from app.services.storage_backend_service import StorageBackendService
from app.services.subscribe.coordinator import DownloadCoordinator
from app.services.subscribe.management.calendar_service import SubscribeCalendarService
from app.services.subscribe.management.history_service import SubscribeHistoryService
from app.services.subscribe.monitor import SubscriptionMonitor
from app.services.subscribe.strategies.indexer_search import IndexerSearchStrategy
from app.services.subscribe.strategies.queue_search import QueueSearchStrategy
from app.services.subscribe.strategies.rss_feed import RssFeedStrategy
from app.services.subscribe_service import SubscribeService
from app.services.sync_engine import SyncEngine
from app.services.sync_service import SyncService
from app.services.system.backup import BackupRestoreService
from app.services.system.config import IndexerConfigService, MediaServerConfigService, SystemConfigService
from app.services.system.info import (
    NetTestService,
    ProgressService,
    SystemInfoService,
    UserManageService,
    WebSearchService,
)
from app.services.system.lifecycle import SystemLifecycleService
from app.services.system.message import MessageClientService, MessageSenderService
from app.services.tmdb_blacklist_service import TmdbBlacklistService
from app.services.torrentremover_core import TorrentRemoverRepository, TorrentRemoverService
from app.services.transfer.cleanup_service import TransferCleanupService
from app.services.transfer.existence_checker import MediaExistenceChecker
from app.services.transfer.filetransfer_service import FileTransferService
from app.services.transfer.handlers import register_download_completed_handler
from app.services.transfer.history_manager import TransferHistoryManager
from app.services.transfer.path_resolver import TransferPathResolver
from app.services.transfer_coordinator import TransferCoordinator
from app.services.transfer_engine import TransferEngine
from app.services.transfer_history_service import TransferHistoryService
from app.services.transfer_pipeline import TransferPipeline
from app.services.words_service import WordsService
from app.sites import SiteConf, SiteSubtitle
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.sites.site_cookie import SiteCookie
from app.sites.site_favicon_service import SiteFaviconService
from app.sites.site_resolver import SiteResolver
from app.sites.site_userinfo import SiteUserInfo


def _build_infrastructure() -> PluginSandbox:
    """创建 Layer 1 基础设施对象。"""
    plugin_registry = PluginRegistry()
    registry.set(RegistryKey.PLUGIN_REGISTRY, plugin_registry)

    thread_executor = ThreadExecutor.named("default")
    scheduler_core = SchedulerCore()
    apikey_service = APIKeyService(
        key_repo=APIKeyRepositoryAdapter(),
        log_repo=APIKeyLogRepositoryAdapter(),
    )
    registry.set(RegistryKey.APIKEY_SERVICE, apikey_service)
    message = Message(apikey_service=apikey_service)
    site_engine = SiteEngine()
    from app.sites.siteuserinfo.config_api import _api_factory
    from app.sites.siteuserinfo.config_html import _html_config_factory

    site_engine.register_user_info_factory(_api_factory)
    site_engine.register_user_info_factory(_html_config_factory)
    site_cache = SiteCache(site_engine=site_engine)
    message_queue = MessageQueueFactory.create()
    hook_system = HookSystem(plugin_sandbox=None)  # 临时占位，后续替换

    plugin_sandbox = PluginSandbox(
        plugin_registry=plugin_registry,
        message=message,
        scheduler_core=scheduler_core,
        hook_system=hook_system,
        site_engine=site_engine,
        media_service=None,  # 媒体服务尚未创建
        plugin_log_repo=PluginLogRepositoryAdapter(),
    )
    registry.set(RegistryKey.PLUGIN_SANDBOX, plugin_sandbox)

    # 更新 hook_system 的 plugin_sandbox 引用
    hook_system.set_plugin_sandbox(plugin_sandbox)

    event_bus = EventBus(registry=EventHandlerRegistry(), bridge=PluginBridge(hook_system=hook_system))

    registry.set(RegistryKey.THREAD_EXECUTOR, thread_executor)
    registry.set(RegistryKey.EVENT_BUS, event_bus)
    registry.set(RegistryKey.SCHEDULER_CORE, scheduler_core)
    registry.set(RegistryKey.MESSAGE, message)
    registry.set(RegistryKey.SITE_CACHE, site_cache)
    registry.set(RegistryKey.SITE_ENGINE, site_engine)
    registry.set(RegistryKey.HOOK_SYSTEM, hook_system)
    registry.set(RegistryKey.MESSAGE_QUEUE, message_queue)

    return plugin_sandbox


def _build_business_facades(plugin_sandbox: PluginSandbox) -> None:
    """创建 Layer 3 业务 Facade。"""
    # 先注册 TMDB 客户端
    tmdb_client = TmdbClient()
    registry.set(RegistryKey.TMDB_CLIENT, tmdb_client)

    # 注册 Agent 相关对象
    agent_service = AgentService()
    registry.set(RegistryKey.AGENT_SERVICE, agent_service)
    media_recognizer = agent_service.media_recognizer
    registry.set(RegistryKey.MEDIA_RECOGNIZER, media_recognizer)
    registry.set(RegistryKey.SEARCH_INTENT_AGENT, agent_service.search_intent_agent)

    # MediaService 与 MediaServer
    media_service = MediaService(
        tmdb_lookup=TmdbLookup(),
        llm_parser=LLMParser(recognizer=media_recognizer),
    )
    registry.set(RegistryKey.MEDIA_SERVICE, media_service)

    # 回填 plugin_sandbox 的媒体服务引用
    plugin_sandbox._media_service = media_service

    media_server = MediaServer(
        media_service=media_service,
        message=registry.get(RegistryKey.MESSAGE),
        message_queue=registry.get(RegistryKey.MESSAGE_QUEUE),
    )
    registry.set(RegistryKey.MEDIA_SERVER, media_server)

    # 下载监控
    event_bus = registry.get(RegistryKey.EVENT_BUS)
    download_monitor = DownloadMonitor(
        client_factory=DownloadClientFactory(),
        event_bus=event_bus,
    )
    registry.set(RegistryKey.DOWNLOAD_MONITOR, download_monitor)


def _build_services() -> None:
    """创建 Layer 4 业务 Service。"""
    agent_service = registry.get(RegistryKey.AGENT_SERVICE)
    download_monitor = registry.get(RegistryKey.DOWNLOAD_MONITOR)
    event_bus = registry.get(RegistryKey.EVENT_BUS)
    media_server = registry.get(RegistryKey.MEDIA_SERVER)
    media_service = registry.get(RegistryKey.MEDIA_SERVICE)
    message = registry.get(RegistryKey.MESSAGE)
    scheduler_core = registry.get(RegistryKey.SCHEDULER_CORE)
    site_cache = registry.get(RegistryKey.SITE_CACHE)
    site_engine = registry.get(RegistryKey.SITE_ENGINE)
    thread_executor = registry.get(RegistryKey.THREAD_EXECUTOR)

    siteconf = SiteConf(site_engine=site_engine)
    sitesubtitle = SiteSubtitle(siteconf=siteconf, sites=site_cache, site_engine=site_engine)

    transfer_engine = TransferEngine()

    media_config_service = MediaConfigService(repo=MediaConfigRepositoryAdapter())
    registry.set(RegistryKey.MEDIA_CONFIG_SERVICE, media_config_service)

    path_resolver = TransferPathResolver.from_settings(media_config_service=media_config_service)
    existence_checker = MediaExistenceChecker(path_resolver=path_resolver)
    history_manager = TransferHistoryManager()
    cleanup_service = TransferCleanupService(
        history_manager=history_manager,
        path_resolver=path_resolver,
        media_service=media_service,
        message=message,
        event_bus=event_bus,
    )

    filetransfer_service = FileTransferService(
        media_service=media_service,
        message=message,
        scraper=Scraper(media_service=media_service),
        thread_executor=thread_executor,
        history_manager=history_manager,
        progress=ProgressTracker(),
        event_bus=event_bus,
        engine=transfer_engine,
        sync_path_repo=SyncPathRepositoryAdapter(),
        path_resolver=path_resolver,
        existence_checker=existence_checker,
        cleanup_service=cleanup_service,
    )
    registry.set(RegistryKey.FILETRANSFER_SERVICE, filetransfer_service)

    transfer_pipeline = TransferPipeline(
        filetransfer=filetransfer_service,
        scraper=Scraper(media_service=media_service),
        blacklist_repo=TransferBlacklistRepositoryAdapter(),
        backend_repo=StorageBackendRepositoryAdapter(),
    )
    register_download_completed_handler(event_bus=event_bus, transfer_pipeline=transfer_pipeline)

    siteconf = SiteConf(site_engine=site_engine)
    sitesubtitle = SiteSubtitle(siteconf=siteconf, sites=site_cache, site_engine=site_engine)

    download_core = DownloadCore(
        client_factory=DownloadClientFactory(),
        message=message,
        mediaserver=media_server,
        filetransfer=filetransfer_service,
        sites=site_cache,
        siteconf=siteconf,
        sitesubtitle=sitesubtitle,
        event_bus=event_bus,
        download_repo=DownloadHistoryRepositoryAdapter(),
        download_setting_repo=DownloadSettingRepositoryAdapter(),
        systemconfig=SystemConfig(),
        downloader_repo=DownloaderRepositoryAdapter(),
        site_engine=site_engine,
    )

    downloader_core = DownloaderCore(
        client_factory=DownloadClientFactory(),
        transfer_coordinator=TransferCoordinator(scheduler=registry.get(RegistryKey.SCHEDULER_CORE)),
        transfer_pipeline=transfer_pipeline,
        download_core=download_core,
    )
    registry.set(RegistryKey.DOWNLOADER_CORE, downloader_core)

    filter_service = FilterService(
        filter_group_repo=FilterGroupRepositoryAdapter(),
        filter_rule_repo=FilterRuleRepositoryAdapter(),
        rg_matcher=ReleaseGroupsMatcher(),
    )
    registry.set(RegistryKey.FILTER_SERVICE, filter_service)

    search_pipeline = SearchPipeline(media_service=media_service)

    indexer = Indexer(
        search_pipeline=search_pipeline,
        indexer_helper=IndexerHelper(),
        site_cache=site_cache,
        site_engine=site_engine,
    )

    indexer_service = IndexerService(
        indexer=indexer,
        indexer_helper=IndexerHelper(),
        site_cache=site_cache,
        site_engine=site_engine,
        indexer_statistics_repo=IndexerStatisticsRepositoryAdapter(),
        string_utils=string_utils_module,
    )
    registry.set(RegistryKey.INDEXER_SERVICE, indexer_service)

    subscribe_service = SubscribeService(
        movie_repo=SubscribeMovieRepositoryAdapter(),
        tv_repo=SubscribeTvRepositoryAdapter(),
        tv_episode_repo=SubscribeTvEpisodeRepositoryAdapter(),
        history_repo=SubscribeHistoryRepositoryAdapter(),
        message=message,
        media_service=media_service,
        downloader=downloader_core,
        sites=site_cache,
        douban=DouBan(),
        indexer_service=indexer_service,
        filter_service=filter_service,
        event_bus=event_bus,
        system_config=SystemConfig(),
    )
    registry.set(RegistryKey.SUBSCRIBE_SERVICE, subscribe_service)

    searcher = Searcher(
        download_repo=DownloadHistoryRepositoryAdapter(),
        search_repo=SearchRepositoryAdapter(),
        downloader=downloader_core,
        media_service=media_service,
        message=message,
        progress_helper=ProgressTracker(),
        indexer_service=indexer_service,
        event_bus=event_bus,
    )
    registry.set(RegistryKey.SEARCHER, searcher)

    sync_engine = SyncEngine(
        transfer_engine=transfer_engine,
        transfer_pipeline=transfer_pipeline,
        sync_path_repo=SyncPathRepositoryAdapter(),
        storage_backend_repo=StorageBackendRepositoryAdapter(),
    )
    registry.set(RegistryKey.SYNC_ENGINE, sync_engine)

    sync_service = SyncService(
        sync=sync_engine,
        filetransfer=filetransfer_service,
        media_cache=MediaCache(),
        thread_executor=thread_executor,
        storage_backend_repo=StorageBackendRepositoryAdapter(),
    )
    registry.set(RegistryKey.SYNC_SERVICE, sync_service)

    file_index_service = FileIndexService(sync_path_repo=SyncPathRepositoryAdapter())
    registry.set(RegistryKey.FILE_INDEX_SERVICE, file_index_service)

    torrent_remover = TorrentRemoverService(
        repository=TorrentRemoverRepository(config_repo=TorrentRemoveTaskRepositoryAdapter()),
        downloader=downloader_core,
        message=message,
        scheduler=registry.get(RegistryKey.SCHEDULER_CORE),
    )
    registry.set(RegistryKey.TORRENTREMOVER_SERVICE, torrent_remover)

    rss_task_service = RssTaskService(
        config_repo=UserRssConfigRepositoryAdapter(),
        rss_repo=SubscribeHistoryRepositoryAdapter(),
        rsshelper=RssHelper(site_engine=site_engine),
        message=message,
        searcher=searcher,
        filter_=filter_service,
        media=media_service,
        downloader=downloader_core,
        scheduler_core=registry.get(RegistryKey.SCHEDULER_CORE),
        site_engine=site_engine,
        event_bus=event_bus,
    )
    registry.set(RegistryKey.RSS_TASK_SERVICE, rss_task_service)

    # 轻量级 Service
    registry.set(RegistryKey.CONFIG_SERVICE, ConfigService())
    registry.set(RegistryKey.MESSAGE_SENDER_SERVICE, MessageSenderService())
    registry.set(RegistryKey.SYSTEM_INFO_SERVICE, SystemInfoService())
    registry.set(RegistryKey.NET_TEST_SERVICE, NetTestService())
    registry.set(RegistryKey.PROGRESS_SERVICE, ProgressService())
    registry.set(
        RegistryKey.WEB_SEARCH_SERVICE,
        WebSearchService(
            searcher=searcher,
            progress_helper=ProgressTracker(),
            media_service=media_service,
            intent_agent=registry.get(RegistryKey.SEARCH_INTENT_AGENT),
        ),
    )
    registry.set(RegistryKey.BACKUP_RESTORE_SERVICE, BackupRestoreService())
    rbac_service = RBACService()
    registry.set(RegistryKey.RBAC_SERVICE, rbac_service)
    registry.set(RegistryKey.USER_RSS_SERVICE, UserRssService(rss_checker=rss_task_service))

    douban = DouBan()
    media_info_service = MediaInfoService(
        media_service=media_service,
        subscribe=subscribe_service,
        media_server=media_server,
        douban=douban,
    )
    registry.set(RegistryKey.MEDIA_INFO_SERVICE, media_info_service)

    registry.set(
        RegistryKey.DOWNLOAD_SERVICE,
        DownloadService(
            downloader=downloader_core,
            searcher=searcher,
            media_service=media_service,
            sites=site_cache,
            site_engine=site_engine,
            indexer_service=indexer_service,
            torrent_remover=torrent_remover,
            download_history_repo=DownloadHistoryRepositoryAdapter(),
        ),
    )
    registry.set(
        RegistryKey.PLUGIN_FRAMEWORK_SERVICE,
        PluginFrameworkService(
            repo=PluginFrameworkRepository(),
            menu_repo=RBACMenuRepositoryAdapter(),
            role_repo=RBACRoleRepositoryAdapter(),
            plugin_registry=registry.get(RegistryKey.PLUGIN_REGISTRY),
            plugin_sandbox=registry.get(RegistryKey.PLUGIN_SANDBOX),
            hook_system=registry.get(RegistryKey.HOOK_SYSTEM),
        ),
    )
    registry.set(
        RegistryKey.STORAGE_BACKEND_SERVICE,
        StorageBackendService(
            repo=StorageBackendRepositoryAdapter(),
        ),
    )
    registry.set(
        RegistryKey.SCHEDULER_SERVICE,
        SchedulerService(
            scheduler_core=registry.get(RegistryKey.SCHEDULER_CORE),
        ),
    )
    registry.set(
        RegistryKey.TMDB_BLACKLIST_SERVICE,
        TmdbBlacklistService(
            media_service=media_service,
        ),
    )

    # 媒体相关 Service
    media_config_service = MediaConfigService(repo=MediaConfigRepositoryAdapter())
    registry.set(RegistryKey.MEDIA_CONFIG_SERVICE, media_config_service)
    registry.set(
        RegistryKey.MEDIA_SERVER_CONFIG_SERVICE,
        MediaServerConfigService(
            config_repo=MediaServerRepositoryAdapter(),
            media_server=media_server,
        ),
    )
    registry.set(
        RegistryKey.MEDIA_FILE_SERVICE,
        MediaFileService(
            event_bus=event_bus,
            storage_backend_repo=StorageBackendRepositoryAdapter(),
            media_service=media_service,
            thread_executor=thread_executor,
            scraper=Scraper(media_service=media_service),
        ),
    )
    registry.set(
        RegistryKey.MEDIA_LIBRARY_SERVICE,
        MediaLibraryService(
            media_server=media_server,
            filetransfer=filetransfer_service,
            system_config=SystemConfig(),
            thread_executor=thread_executor,
            media_config_service=media_config_service,
        ),
    )
    registry.set(
        RegistryKey.MEDIA_RECOMMENDATION_SERVICE,
        MediaRecommendationService(
            media_service=media_service,
            douban=douban,
            bangumi=Bangumi(),
            media_server=media_server,
            subscribe=subscribe_service,
            media_info_service=media_info_service,
            downloader_core=downloader_core,
        ),
    )

    # 系统 Service
    registry.set(RegistryKey.SYSTEM_CONFIG_SERVICE, SystemConfigService())
    registry.set(
        RegistryKey.INDEXER_CONFIG_SERVICE,
        IndexerConfigService(
            indexer_service=indexer_service,
            indexer=indexer_service.indexer,
        ),
    )
    registry.set(
        RegistryKey.USER_MANAGE_SERVICE,
        UserManageService(
            rbac_svc=rbac_service,
        ),
    )
    registry.set(RegistryKey.MESSAGE_CLIENT_SERVICE, MessageClientService(message=message))

    # 刷流 Service
    brush_task_service = BrushTaskService(
        repository=BrushTaskRepositoryAdapter(),
        scheduler=BrushTaskScheduler(scheduler=registry.get(RegistryKey.SCHEDULER_CORE)),
        downloader=downloader_core,
        message=message,
        sites=site_cache,
        siteconf=siteconf,
        site_engine=site_engine,
        rsshelper=RssHelper(site_engine=site_engine),
        filter_service=filter_service,
        brush_rule_repo=BrushRuleRepositoryAdapter(),
        media_service=media_service,
    )
    registry.set(RegistryKey.BRUSH_TASK_SERVICE, brush_task_service)
    registry.set(
        RegistryKey.BRUSH_SERVICE,
        BrushService(
            brush_task=brush_task_service,
            rule_repo=BrushRuleRepositoryAdapter(),
        ),
    )

    # 站点 Service
    site_favicon_service = SiteFaviconService(
        cache=site_cache,
        site_engine=site_engine,
        repo=SiteRepository(),
    )
    registry.set(RegistryKey.SITE_FAVICON_SERVICE, site_favicon_service)

    site_userinfo = SiteUserInfo(
        site_cache=site_cache,
        site_repository=SiteRepository(),
        site_favicon_service=site_favicon_service,
        site_engine=site_engine,
    )
    site_resolver = SiteResolver(cache=site_cache, site_engine=site_engine)
    registry.set(RegistryKey.SITE_RESOLVER, site_resolver)
    registry.set(
        RegistryKey.SITE_SERVICE,
        SiteService(
            sites=site_cache,
            site_user_info=site_userinfo,
            site_conf=siteconf,
            indexer_service=indexer_service,
            site_repo=SiteRepository(),
            site_favicon_service=site_favicon_service,
            site_resolver=site_resolver,
            site_cookie=SiteCookie(sites=site_cache, site_engine=site_engine),
            string_utils=string_utils_module,
            site_entity_repo=SiteRepositoryAdapter(),
        ),
    )

    # 创建 ToolExecutor 并注入 AgentService（解决循环依赖）
    agent_service = registry.get(RegistryKey.AGENT_SERVICE)
    tool_executor = ToolExecutor(
        message=message,
        thread_executor=thread_executor,
        scheduler_core=scheduler_core,
        event_bus=event_bus,
        download_monitor=download_monitor,
        filetransfer_service=filetransfer_service,
        rss_helper=RssHelper(site_engine=site_engine),
        search_intent_agent=agent_service.search_intent_agent,
        site_userinfo=site_userinfo,
        scheduler_service=registry.get(RegistryKey.SCHEDULER_SERVICE),
        message_client_service=registry.get(RegistryKey.MESSAGE_CLIENT_SERVICE),
    )
    agent_service.set_tool_executor(tool_executor)


def _build_coordinators() -> None:
    """创建 Layer 5 协调器。"""
    downloader_core = registry.get(RegistryKey.DOWNLOADER_CORE)
    download_monitor = registry.get(RegistryKey.DOWNLOAD_MONITOR)
    file_index_service = registry.get(RegistryKey.FILE_INDEX_SERVICE)
    media_server = registry.get(RegistryKey.MEDIA_SERVER)
    rss_task_service = registry.get(RegistryKey.RSS_TASK_SERVICE)
    scheduler_core = registry.get(RegistryKey.SCHEDULER_CORE)
    site_userinfo = registry.get(RegistryKey.SITE_SERVICE).site_user_info
    subscribe_service = registry.get(RegistryKey.SUBSCRIBE_SERVICE)
    sync_engine = registry.get(RegistryKey.SYNC_ENGINE)
    thread_executor = registry.get(RegistryKey.THREAD_EXECUTOR)
    torrent_remover = registry.get(RegistryKey.TORRENTREMOVER_SERVICE)
    apikey_service = registry.get(RegistryKey.APIKEY_SERVICE)
    searcher = registry.get(RegistryKey.SEARCHER)
    media_service = registry.get(RegistryKey.MEDIA_SERVICE)
    filter_service = registry.get(RegistryKey.FILTER_SERVICE)
    site_cache = registry.get(RegistryKey.SITE_CACHE)
    site_engine = registry.get(RegistryKey.SITE_ENGINE)
    message = registry.get(RegistryKey.MESSAGE)
    siteconf = SiteConf(site_engine=site_engine)

    from app.services.subscribe.matcher import SubscribeMatcher

    download_repo = DownloadHistoryRepositoryAdapter()
    rss_repo = SubscribeHistoryRepositoryAdapter()
    media_cache = MediaCache()
    matcher = SubscribeMatcher(site_conf=siteconf, site_cache=site_cache)
    queue_strategy = QueueSearchStrategy(
        service=subscribe_service,
        searcher=searcher,
        media_service=media_service,
        media_cache=media_cache,
        downloader=downloader_core,
        filter_service=filter_service,
        message=message,
    )
    rsshelper = RssHelper(site_engine=site_engine)
    rss_strategy = RssFeedStrategy(
        media=media_service,
        downloader=downloader_core,
        sites=site_cache,
        siteconf=siteconf,
        download_repo=download_repo,
        rss_repo=rss_repo,
        rsshelper=rsshelper,
        subscribe=subscribe_service,
        matcher=matcher,
        message=message,
    )
    indexer_strategy = IndexerSearchStrategy(
        service=subscribe_service,
        searcher=searcher,
        media_service=media_service,
        media_cache=media_cache,
        downloader=downloader_core,
        filter_service=filter_service,
        message=message,
    )
    subscription_monitor = SubscriptionMonitor(
        subscribe_service=subscribe_service,
        thread_executor=thread_executor,
        queue_strategy=queue_strategy,
        rss_strategy=rss_strategy,
        indexer_strategy=indexer_strategy,
        coordinator=DownloadCoordinator(),
    )

    system_lifecycle = SystemLifecycleService(
        scheduler_core=scheduler_core,
        download_monitor=download_monitor,
        sync=sync_engine,
        brush_task_service=None,  # TODO: 待 BrushTaskService 工厂完成后注入
        rss_checker=rss_task_service,
        torrent_remover=torrent_remover,
        downloader=downloader_core,
        file_index_service=file_index_service,
        subscription_monitor=subscription_monitor,
        site_userinfo=site_userinfo,
        subscribe_service=subscribe_service,
        media_server=media_server,
        thread_executor=thread_executor,
        apikey_service=apikey_service,
    )
    registry.set(RegistryKey.SYSTEM_LIFECYCLE, system_lifecycle)


def _register_post_db_services() -> None:
    """注册需要在数据库初始化后构造的服务。"""
    media_info_service = registry.get(RegistryKey.MEDIA_INFO_SERVICE)
    rss_task_service = registry.get(RegistryKey.RSS_TASK_SERVICE)
    site_engine = registry.get(RegistryKey.SITE_ENGINE)
    subscribe_service = registry.get(RegistryKey.SUBSCRIBE_SERVICE)
    sync_service = registry.get(RegistryKey.SYNC_SERVICE)
    filetransfer_service = registry.get(RegistryKey.FILETRANSFER_SERVICE)

    registry.set(
        RegistryKey.WORDS_SERVICE,
        WordsService(
            media_cache=MediaCache(),
            word_repo=CustomWordRepositoryAdapter(),
            group_repo=CustomWordGroupRepositoryAdapter(),
        ),
    )
    registry.set(
        RegistryKey.SUBSCRIBE_CALENDAR_SERVICE,
        SubscribeCalendarService(
            media_info_service=media_info_service,
            subscribe=subscribe_service,
            rss_task_service=rss_task_service,
        ),
    )
    registry.set(
        RegistryKey.SUBSCRIBE_HISTORY_SERVICE,
        SubscribeHistoryService(
            history_repo=SubscribeHistoryRepositoryAdapter(),
            subscribe=subscribe_service,
            rss_helper=RssHelper(site_engine=site_engine),
        ),
    )
    registry.set(
        RegistryKey.SEARCH_RESULT_SERVICE,
        SearchResultService(
            media_server=registry.get(RegistryKey.MEDIA_SERVER),
            subscribe=subscribe_service,
        ),
    )
    registry.set(
        RegistryKey.TRANSFER_HISTORY_SERVICE,
        TransferHistoryService(
            filetransfer=filetransfer_service,
            sync_service=sync_service,
        ),
    )


def build_all() -> None:
    """按拓扑顺序创建所有对象并注册到 registry。"""
    log.info("[DI]开始构建对象图...")
    plugin_sandbox = _build_infrastructure()
    _build_business_facades(plugin_sandbox=plugin_sandbox)
    _build_services()
    _build_coordinators()
    _register_post_db_services()
    log.info("[DI]对象图构建完成")


def init_site_config() -> None:
    """初始化站点配置（需要在数据库初始化后执行）。"""
    log.info("[FastAPI]初始化站点配置...")
    try:
        updater = SiteConfigUpdater()
        updater.ensure_local_sites(SiteEngine._BUILTIN_DEFINITIONS_DIR)
        update_site_config_at_startup()
    except Exception as e:
        log.warn(f"[FastAPI]站点配置初始化失败: {e!s}")
