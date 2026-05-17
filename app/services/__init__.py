"""
Service 层：业务用例编排，脱离 Web 框架可独立运行
"""

from .brush_core import BrushTaskRepository, BrushTaskScheduler, BrushTaskService
from .brush_service import BrushService
from .config_service import ConfigService
from .download_service import DownloadService
from .filter_service import FilterService
from .indexer_service import IndexerService
from .media_service import (
    MediaFileService,
    MediaInfoService,
    MediaLibraryService,
    MediaRecommendationService,
    SearchResultService,
    TransferHistoryService,
)
from .rss_core import Rss
from .rss_service import RssParserEngine, RssSubscriptionService, RssTaskService
from .search_service import Searcher, SearchService
from .site_service import SiteService
from .sync_engine import SyncEngine
from .sync_service import SyncService
from .system_service import (
    BackupRestoreService,
    IndexerConfigService,
    MediaServerConfigService,
    MessageClientService,
    MessageCommandHandler,
    NetTestService,
    SchedulerService,
    SystemConfigService,
    SystemLifecycleService,
    VersionService,
    WebSearchService,
    backup,
    get_commands,
    get_rmt_modes,
    get_system_message,
    parse_brush_rule_string,
)
from .torrentremover_core import TorrentRemoverService
from .userrss_service import UserRssService
from .words_service import WordsService
