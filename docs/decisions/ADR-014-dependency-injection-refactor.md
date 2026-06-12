# ADR-014: 依赖注入架构重构 — 从 Service Locator 到分层显式依赖

## Status

Proposed

## Date

2026-06-10

---

## Context

### 当前问题

项目使用 `dependency-injector` 的 `DeclarativeContainer` 管理约 270 个 provider，在 135 个文件中被直接调用 459 次。这种模式本质上是 **Service Locator 反模式**，产生以下问题：

1. **隐藏依赖**：Service 的 `__init__` 参数全为 `None`，依赖关系散落在 `or container.xxx()` 中，无法通过签名读取
2. **单例滥用**：270 个 provider 中有约 85% 被注册为 Singleton，但 Repository、Strategy、无状态 Service 根本不需要单例
3. **测试困难**：需要 `override`/`reset_override` 全局状态，测试间相互污染
4. **生命周期不可控**：基础设施（EventBus、HttpClient、Scheduler）的创建和关闭隐藏在 Container 内，lifespan 无法显式管理
5. **插件硬编码**：21 个内置插件在 `__init__` 中直接调用 `container.xxx()`，无注入参数

### 引用现状

`from app.di import container` 被 135 个文件引用：

| 模块 | 文件数 | 问题 |
|------|--------|------|
| `app/services/` | 40+ | `or container.xxx()` fallback |
| `app/plugin_framework/builtin_plugins/` | 21 | 构造函数硬编码 container |
| `app/media/` | 8 | 方法内部调用 container |
| `app/message/` | 5 | 客户端内部调用 container |
| `app/events/` | 1 | `@on_event` 装饰器导入即触发 |

### 单例滥用现状

当前 Container 注册了 270+ 个 provider，但实际需要单例的不到 15 个。Repository、Strategy、轻量 Helper 全部被注册为 Singleton，导致：

- 内存中常驻大量不必要的对象
- 测试时 `reset_override` 需要清理整个容器
- 新开发者难以判断哪些对象可以安全地 `new`，哪些必须走 Container

---

## Goals

1. **消除 Service Locator**：Service / Plugin 内部不再调用 `container.xxx()`
2. **显式依赖声明**：所有依赖通过 `__init__` 参数传入，类型签名即文档
3. **单例按需**：只有真正有共享状态/资源的对象才使用单例，其余每次创建
4. **生命周期可控**：基础设施单例的创建和关闭由 lifespan 显式管理
5. **渐进迁移**：新旧模式共存，按文件逐步替换

---

## Decision

### 架构：三层模型

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: Composition Root (lifespan / api/deps)            │
│  职责：创建基础设施单例 → 注入业务单例 → 组装无状态 Service     │
│         ↓ 关闭时反向清理                                     │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Business Services                                 │
│  app/services/*, app/media/*, app/message/*                 │
│  职责：业务逻辑，只通过 __init__ 接收依赖                    │
│  注入方式：@inject + Provide[Container.xxx]                  │
│  禁止：调用 container、import deps                           │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: Infrastructure Singletons                         │
│  EventBus, HttpClient, ThreadExecutor, SchedulerCore        │
│  Message, SiteCache, SiteEngine, ConfigReloader             │
│  职责：资源管理，自管生命周期                                │
│  暴露：get_instance() / close_instance()                     │
│  lifespan 直接调用，不通过 Container                         │
└──────────────────────────────────────────────────────────────┘
```

### 核心设计决策

#### 1. 基础设施单例：自托管

有共享状态/资源的对象，由类自身管理生命周期，lifespan 中显式创建和关闭。

```python
# app/events/bus.py
class EventBus:
    _instance: EventBus | None = None

    @classmethod
    def get_instance(cls, *, registry=None, queue=None) -> EventBus:
        if cls._instance is None:
            cls._instance = cls(
                registry=registry or EventHandlerRegistry(),
                queue=queue or MessageQueueFactory.create(),
            )
        return cls._instance

    @classmethod
    def close_instance(cls) -> None:
        if cls._instance:
            cls._instance.shutdown()
            cls._instance = None
```

```python
# app/infrastructure/http/client.py
class HttpClient:
    _instance: HttpClient | None = None

    @classmethod
    def get_instance(cls) -> HttpClient:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def close_instance(cls) -> None:
        if cls._instance:
            cls._instance.close()
            cls._instance = None
```

```python
# app/services/scheduler/core.py
class SchedulerCore:
    _instance: SchedulerCore | None = None

    @classmethod
    def get_instance(cls) -> SchedulerCore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def close_instance(cls) -> None:
        if cls._instance:
            cls._instance.stop_service()
            cls._instance = None
```

**自托管单例清单**：

| 类 | 共享状态/资源 | 生命周期管理 |
|----|-------------|------------|
| EventBus | 事件处理器注册表 | lifespan 创建 → 关闭 |
| HttpClient | httpx.Client 连接池 | lifespan 创建 → 关闭 |
| AsyncHttpClient | httpx.AsyncClient 连接池 | lifespan 创建 → 关闭 |
| ThreadExecutor | ThreadPoolExecutor | lifespan 创建 → shutdown |
| SchedulerCore | BackgroundScheduler + 任务注册表 | lifespan 创建 → stop |
| Message | ClientManager 配置 + MessageCenter 队列 | lifespan 创建 → 清理 |
| SiteCache | 内存索引 dict | lifespan 创建 → 刷新 |
| SiteEngine | 站点定义 + 工厂注册表 | lifespan 创建 → 重置 |
| ConfigReloader | 重载步骤 + 版本号 | lifespan 创建 |
| PluginRegistry | 插件注册表 | lifespan 创建 |
| HookSystem | 钩子订阅 | lifespan 创建 |
| PluginSandbox | 插件实例缓存 | lifespan 创建 → 清理 |
| MediaServer | 客户端连接状态 | lifespan 创建 → 关闭 |
| DownloadMonitor | 后台监控状态 | lifespan 创建 → 停止 |
| SyncEngine | watchdog Observer + 配置缓存 | lifespan 创建 → 停止 |

#### SiteEngine 改造示例

SiteEngine 是当前调用最分散的单例，30+ 处直接调用 `SiteEngine.get_instance()`。需要保留 `get_instance()` 作为自托管入口，但限制调用位置。

**改造前**：

```python
# app/sites/engine.py
class SiteEngine:
    _engine_instance: Optional["SiteEngine"] = None

    @classmethod
    def get_instance(cls, definitions_dir: str | None = None) -> "SiteEngine":
        if cls._engine_instance is None:
            cls._engine_instance = cls(definitions_dir)
            cls._engine_instance._register_user_info_factories()
        return cls._engine_instance


# app/services/download_core.py（方法内部直接调用）
def resolve_download_url(self, url):
    site_def = SiteEngine.get_instance().get_by_url(url)
    return site_def.download.url_format.format(tid=tid)


# app/services/brush/helpers.py（方法内部直接调用）
def _parse_site(self, site_id):
    engine = SiteEngine.get_instance()
    site_def = engine.get_by_id(site_id)
    ...
```

**改造后**：自托管 + 构造函数注入

```python
# app/sites/engine.py
class SiteEngine:
    _engine_instance: Optional["SiteEngine"] = None

    @classmethod
    def get_instance(cls, definitions_dir: str | None = None) -> "SiteEngine":
        if cls._engine_instance is None:
            cls._engine_instance = cls(definitions_dir)
            cls._engine_instance._register_user_info_factories()
        return cls._engine_instance

    @classmethod
    def close_instance(cls) -> None:
        cls._engine_instance = None

    @classmethod
    def reset_instance(cls) -> None:
        """测试时重置"""
        cls._engine_instance = None


# app/services/download_core.py
class DownloadCore:
    @inject
    def __init__(
        self,
        site_engine: SiteEngine = Provide[Container.site_engine],
        ...
    ):
        self._site_engine = site_engine

    def resolve_download_url(self, url):
        site_def = self._site_engine.get_by_url(url)
        return site_def.download.url_format.format(tid=tid)


# app/services/brush/helpers.py
class BrushHelper:
    @inject
    def __init__(
        self,
        site_engine: SiteEngine = Provide[Container.site_engine],
        ...
    ):
        self._site_engine = site_engine

    def _parse_site(self, site_id):
        site_def = self._site_engine.get_by_id(site_id)
        ...
```

**Container 注册**：

```python
class Container(containers.DeclarativeContainer):
    # SiteEngine 是自托管单例，通过 override 注入
    site_engine = providers.Singleton(lambda: _not_bound("site_engine"))
```

**lifespan 绑定**：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    site_engine = SiteEngine.get_instance()
    container.site_engine.override(providers.Singleton(lambda: site_engine))
    ...
```

**调用位置限制**：

| 允许调用 | 禁止调用 |
|---------|---------|
| `lifespan` 中创建 | Service 方法内部 |
| `api/deps.py` 组装 | 插件内部 |
| 测试 fixture 中 reset | 工具函数/静态方法 |
| `get_tid_by_url` 等纯函数（过渡期） | Repository 内部 |

**过渡期处理**：

`get_tid_by_url` 等模块级函数无法接收构造函数注入，可保留 `SiteEngine.get_instance()` 调用作为过渡，但需标记为 `@deprecated`：

```python
def get_tid_by_url(url: str, site_engine: SiteEngine | None = None) -> str | None:
    """从下载链接提取种子 ID"""
    engine = site_engine or SiteEngine.get_instance()
    site_def = engine.get_by_url(url)
    ...
```

#### 2. 有状态业务对象：Container Singleton + @inject

有内部缓存但非基础设施的对象，通过 `@inject` 注入基础设施引用。

```python
# app/media/service.py
from dependency_injector.wiring import inject, Provide
from app.di.container import Container

class MediaService:
    @inject
    def __init__(
        self,
        tmdb_lookup: TmdbLookup = Provide[Container.tmdb_lookup],
        llm_parser: LLMParser = Provide[Container.llm_parser],
        tmdb_client: TmdbClient = Provide[Container.tmdb_client],
    ):
        self._lookup = tmdb_lookup
        self._llm_parser = llm_parser
        self._tmdb_client = tmdb_client
```

**有状态业务单例清单**：

| 类 | 内部状态 | 注册方式 |
|----|---------|---------|
| MediaService | TmdbLookup 缓存 | Singleton |
| TmdbClient | 查询结果缓存 | Singleton |
| TmdbLookup | TMDB 请求缓存 | Singleton |
| DouBan | 请求缓存 | Singleton |
| Bangumi | 请求缓存 | Singleton |
| Scraper | 元数据缓存 | Singleton |
| Fanart | 图片元数据缓存 | Singleton |
| MediaCache | 显式缓存对象 | Singleton |
| WordsService | 识别词规则缓存 | Singleton |
| SiteUserInfo | 站点用户信息缓存 | Singleton |
| SiteConf | 站点配置缓存 | Singleton |

#### 3. 无状态业务 Service：Container Factory + @inject

无共享状态的对象，每次创建新实例。

```python
# app/services/transfer/filetransfer_service.py
class FileTransferService:
    @inject
    def __init__(
        self,
        media_service: MediaService = Provide[Container.media_service],
        scraper: Scraper = Provide[Container.scraper],
        event_bus: EventBus = Provide[Container.event_bus],
    ):
        self._media = media_service
        self._scraper = scraper
        self._event_bus = event_bus
```

**注意**：`EventBus` 是基础设施单例，不在 Container 中注册。通过 lifespan 中 `override` 注入：

```python
# api/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 基础设施自管创建
    event_bus = EventBus.get_instance()
    thread_executor = ThreadExecutor.named("default")
    message = Message.get_instance()

    # 2. 基础设施注入到 Container（供 @inject 使用）
    container.event_bus.override(providers.Singleton(lambda: event_bus))
    container.thread_executor.override(providers.Singleton(lambda: thread_executor))
    container.message.override(providers.Singleton(lambda: message))

    # 3. 触发 @inject 绑定
    container.wire_modules()

    yield

    # 4. 反向清理
    container.event_bus.reset_override()
    Message.close_instance()
    EventBus.close_instance()
    ThreadExecutor.shutdown_all()
```

#### 4. Repository：每次创建，不传单例

Repository 是轻量对象，不持有连接，通过 SQLAlchemy session 共享连接。

```python
class SiteRepositoryAdapter(ISiteRepository):
    def __init__(self):
        # 不接收 session，每次方法内部获取
        pass
```

**不在 Container 中注册**，由需要它的 Service 在 `__init__` 中直接 `new`：

```python
class SyncEngine:
    def __init__(
        self,
        sync_path_repo: SyncPathRepositoryAdapter = Provide[Container.sync_path_repo],
        storage_backend_repo: StorageBackendRepositoryAdapter = Provide[Container.storage_backend_repo],
    ):
        self._sync_repo = sync_path_repo  # Container 提供，但内部是 Factory
```

Container 中注册为 `Factory`：

```python
class Container(containers.DeclarativeContainer):
    sync_path_repo = providers.Factory(SyncPathRepositoryAdapter)
    storage_backend_repo = providers.Factory(StorageBackendRepositoryAdapter)
```

#### 5. 插件依赖注入：PluginContext

插件不再硬编码 `container.xxx()`，通过 `PluginContext` 接收依赖。

```python
# app/plugin_framework/context.py
class PluginContext:
    """插件运行时的依赖上下文 — 由 PluginSandbox 在初始化时注入。"""

    @inject
    def __init__(
        self,
        douban: DouBan = Provide[Container.douban],
        searcher: Searcher = Provide[Container.searcher],
        downloader: DownloaderCore = Provide[Container.downloader_core],
        message: Message = Provide[Container.message],
        site_cache: SiteCache = Provide[Container.site_cache],
    ):
        self.douban = douban
        self.searcher = searcher
        self.downloader = downloader
        self.message = message
        self.site_cache = site_cache
```

```python
# app/plugin_framework/builtin_plugins/doubansync/backend/plugin.py
class DoubanSyncPlugin:
    def __init__(self, context: PluginContext):
        self._douban = context.douban
        self._searcher = context.searcher
        self._downloader = context.downloader
```

#### 6. 单例分类决策表

| 类别 | 判定标准 | 管理方式 | Container 注册 |
|------|---------|---------|---------------|
| **基础设施单例** | 外部资源（线程池、连接池、调度器）、全局注册表、队列 | 自托管 `get_instance()` | ❌ 不注册，lifespan override |
| **有状态业务单例** | 内部缓存、配置缓存、运行时状态 | `@inject` + Singleton | ✅ Singleton |
| **无状态 Service** | 纯协调逻辑，无内部状态 | `@inject` + Factory | ✅ Factory |
| **Repository** | 数据访问，无状态 | 每次 `new` | ✅ Factory |
| **Strategy/Helper** | 算法/工具，无状态 | 每次 `new` | ✅ Factory |

---

## 详细设计

### Container 精简后

```python
# app/di/container.py
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    # ── 基础设施占位符（lifespan 中 override）──
    event_bus = providers.Singleton(lambda: _not_bound("event_bus"))
    thread_executor = providers.Singleton(lambda: _not_bound("thread_executor"))
    message = providers.Singleton(lambda: _not_bound("message"))

    # ── 有状态业务单例 ──
    media_service = providers.Singleton(MediaService)
    tmdb_client = providers.Singleton(TmdbClient)
    tmdb_lookup = providers.Singleton(TmdbLookup)
    douban = providers.Singleton(DouBan)
    bangumi = providers.Singleton(Bangumi)
    scraper = providers.Singleton(Scraper)
    fanart = providers.Singleton(Fanart)
    media_cache = providers.Singleton(MediaCache)
    words_service = providers.Singleton(WordsService)
    site_userinfo = providers.Singleton(SiteUserInfo)
    site_conf = providers.Singleton(SiteConf)

    # ── 无状态 Service（Factory）──
    sync_engine = providers.Factory(SyncEngine)
    filetransfer_service = providers.Factory(FileTransferService)
    transfer_engine = providers.Factory(TransferEngine)
    search_service = providers.Factory(SearchService)
    download_service = providers.Factory(DownloadService)
    indexer_service = providers.Factory(IndexerService)
    filter_service = providers.Factory(FilterService)
    site_service = providers.Factory(SiteService)
    brush_service = providers.Factory(BrushService)
    brush_task_service = providers.Factory(BrushTaskService)
    rss_task_service = providers.Factory(RssTaskService)
    subscribe_service = providers.Factory(SubscribeService)
    transfer_history_service = providers.Factory(TransferHistoryService)
    media_info_service = providers.Factory(MediaInfoService)
    media_library_service = providers.Factory(MediaLibraryService)
    media_recommendation_service = providers.Factory(MediaRecommendationService)
    media_file_service = providers.Factory(MediaFileService)
    search_result_service = providers.Factory(SearchResultService)
    file_index_service = providers.Factory(FileIndexService)
    config_service = providers.Factory(ConfigService)
    scheduler_service = providers.Factory(SchedulerService)
    system_lifecycle_service = providers.Factory(SystemLifecycleService)

    # ── Repository（Factory）──
    site_repository = providers.Factory(SiteRepository)
    site_repo_adapter = providers.Factory(SiteRepositoryAdapter)
    sync_path_repo = providers.Factory(SyncPathRepositoryAdapter)
    storage_backend_repo = providers.Factory(StorageBackendRepositoryAdapter)
    media_sync_repo = providers.Factory(MediaSyncRepositoryAdapter)
    download_history_repo = providers.Factory(DownloadHistoryRepositoryAdapter)
    downloader_repo = providers.Factory(DownloaderRepositoryAdapter)
    media_server_repo = providers.Factory(MediaServerRepositoryAdapter)
    tmdb_blacklist_repo = providers.Factory(TmdbBlacklistRepositoryAdapter)
    apikey_repo = providers.Factory(APIKeyRepositoryAdapter)
    apikey_log_repo = providers.Factory(APIKeyLogRepositoryAdapter)
    indexer_statistics_repo = providers.Factory(IndexerStatisticsRepositoryAdapter)
    search_repo = providers.Factory(SearchRepositoryAdapter)
    brush_rule_repo = providers.Factory(BrushRuleRepositoryAdapter)
    rbac_permission_repo = providers.Factory(RBACPermissionRepositoryAdapter)
    rbac_menu_repo = providers.Factory(RBACMenuRepositoryAdapter)
    rbac_role_repo = providers.Factory(RBACRoleRepositoryAdapter)
    rbac_user_repo = providers.Factory(RBACUserRepositoryAdapter)
    rss_torrent_repo = providers.Factory(SubscribeTorrentRepositoryAdapter)
    custom_word_repo = providers.Factory(CustomWordRepositoryAdapter)
    custom_word_group_repo = providers.Factory(CustomWordGroupRepositoryAdapter)
    plugin_framework_repo = providers.Factory(PluginFrameworkRepository)
    torrent_remove_task_repo = providers.Factory(TorrentRemoveTaskRepositoryAdapter)
    download_repo = providers.Factory(DownloadRepository)
    filter_group_repo = providers.Factory(FilterGroupRepositoryAdapter)
    filter_rule_repo = providers.Factory(FilterRuleRepositoryAdapter)
    plugin_log_repo = providers.Factory(PluginLogRepositoryAdapter)

    def wire_modules(self):
        """触发 @inject 绑定，在 lifespan 中调用。"""
        from app.services import transfer
        from app.services import sync_engine
        from app.services import download_service
        from app.media import service as media_service_module
        from app.message import message as message_module
        from app.plugin_framework import builtin_plugins
        # ... 所有使用 @inject 的模块
        self.wire(
            modules=[
                transfer.filetransfer_service,
                sync_engine,
                download_service,
                media_service_module,
                message_module,
                # ...
            ]
        )


def _not_bound(name: str):
    raise RuntimeError(f"{name} 尚未绑定，请在 lifespan 中 override")
```

### lifespan 中基础设施绑定

```python
# api/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 基础设施自管创建
    event_bus = EventBus.get_instance()
    http_client = HttpClient.get_instance()
    async_http = AsyncHttpClient.get_instance()
    thread_executor = ThreadExecutor.named("default")
    scheduler_core = SchedulerCore.get_instance()
    message = Message.get_instance()
    site_cache = SiteCache.get_instance()
    site_engine = SiteEngine.get_instance()
    config_reloader = ConfigReloader.get_instance()
    plugin_registry = PluginRegistry.get_instance()
    hook_system = HookSystem.get_instance()
    plugin_sandbox = PluginSandbox.get_instance()
    media_server = MediaServer.get_instance()
    download_monitor = DownloadMonitor.get_instance()
    sync_engine_singleton = SyncEngine.get_instance()

    # 2. 基础设施注入到 Container（供 @inject 使用）
    container.event_bus.override(providers.Singleton(lambda: event_bus))
    container.thread_executor.override(providers.Singleton(lambda: thread_executor))
    container.message.override(providers.Singleton(lambda: message))
    container.site_cache.override(providers.Singleton(lambda: site_cache))

    # 3. 触发 @inject 绑定
    container.wire_modules()

    # 4. 启动业务服务
    sync_engine_singleton.init()
    scheduler_core.start_service(load_defaults=True)
    download_monitor.start()

    yield

    # 5. 反向关闭
    sync_engine_singleton.stop()
    download_monitor.stop()
    scheduler_core.stop_service()
    Message.close_instance()
    EventBus.close_instance()
    HttpClient.close_instance()
    AsyncHttpClient.close_instance()
    ThreadExecutor.shutdown_all()
    container.event_bus.reset_override()
    container.thread_executor.reset_override()
    container.message.reset_override()
    container.site_cache.reset_override()
```

### 测试策略

**测试无状态 Service**：

```python
def test_sync_engine():
    engine = SyncEngine(
        transfer_engine=mock_transfer,
        sync_path_repo=mock_repo,
        storage_backend_repo=mock_backend,
        event_bus=mock_bus,
    )
    ...
```

**测试有状态单例**：

```python
def test_media_service():
    svc = MediaService(
        tmdb_lookup=mock_lookup,
        llm_parser=mock_llm,
        tmdb_client=mock_client,
    )
    ...
```

**测试基础设施**：

```python
def test_event_bus():
    bus = EventBus.get_instance(registry=mock_registry, queue=mock_queue)
    ...
    EventBus.close_instance()  # 清理
```

---

## Migration Path

### Phase 1：基础设施自托管改造（2 天）

1. 为 EventBus、HttpClient、AsyncHttpClient、ThreadExecutor 添加 `get_instance()` / `close_instance()`
2. 为 SchedulerCore、Message、SiteCache、SiteEngine、ConfigReloader、PluginRegistry、HookSystem、PluginSandbox、MediaServer、DownloadMonitor、SyncEngine 添加 `get_instance()` / `close_instance()`
3. 修改 `api/main.py` lifespan，用自托管替代 Container 创建

### Phase 2：Container 精简 + @inject 改造（3 天）

1. 精简 Container：移除基础设施 provider，保留约 35 个业务 provider（15 个 Singleton + 20 个 Factory）
2. 为高频 Service 添加 `@inject`：`MediaService`、`FileTransferService`、`SyncEngine`、`DownloadService`、`SearchService`
3. 删除 Service 内部的 `from app.di import container`

### Phase 3：插件改造（2 天）

1. 完善 `PluginContext`，注入常用依赖
2. 改造 21 个内置插件，移除 `container.xxx()` 硬编码

### Phase 4：清理（1 天）

1. 全局检查 `from app.di import container`，确保仅在 `api/deps.py` 和 `lifespan` 中存在
2. 运行 `uv run ruff check .` 和 `uv run pyright src/ tests/`

---

## Consequences

### 正面影响

1. **依赖可见**：通过 `__init__` 签名即可读取类的全部依赖
2. **单例可控**：基础设施生命周期由 lifespan 显式管理，可测试 close/restart
3. **容器精简**：从 270 个 provider 减至约 35 个，降低认知负担
4. **测试友好**：直接 `new Service(mock_a, mock_b)`，无需 override 全局状态
5. **插件解耦**：PluginContext 统一注入，插件不再硬编码 container

### 负面影响

1. **@inject 样板代码**：每个 Service 需要添加 `@inject` + `Provide[Container.xxx]`
2. **lifespan 膨胀**：基础设施创建逻辑从 Container 移到 lifespan，代码量增加
3. **模块导入顺序**：`wire_modules()` 需要在所有 `@inject` 模块导入后调用

### 缓解措施

- 使用 `pycln` / `autoflake` 自动清理 `from app.di import container`
- lifespan 中基础设施创建可提取为 `init_infrastructure()` / `shutdown_infrastructure()` 辅助函数

---

## 附录：单例完整分类表

### 自托管单例（不在 Container 中注册）

| 类 | 共享状态 | 创建位置 | 关闭位置 |
|----|---------|---------|---------|
| EventBus | 事件处理器注册表 | lifespan | lifespan |
| HttpClient | httpx.Client 连接池 | lifespan | lifespan |
| AsyncHttpClient | httpx.AsyncClient 连接池 | lifespan | lifespan |
| ThreadExecutor | ThreadPoolExecutor | lifespan | lifespan |
| SchedulerCore | BackgroundScheduler + 任务注册表 | lifespan | lifespan |
| Message | ClientManager + MessageCenter 队列 | lifespan | lifespan |
| SiteCache | 内存索引 dict | lifespan | lifespan |
| SiteEngine | 站点定义 + 工厂注册表 | lifespan | lifespan |
| ConfigReloader | 重载步骤 + 版本号 | lifespan | — |
| PluginRegistry | 插件注册表 | lifespan | lifespan |
| HookSystem | 钩子订阅 | lifespan | lifespan |
| PluginSandbox | 插件实例缓存 | lifespan | lifespan |
| MediaServer | 客户端连接状态 | lifespan | lifespan |
| DownloadMonitor | 后台监控状态 | lifespan | lifespan |
| SyncEngine | watchdog Observer + 配置缓存 | lifespan | lifespan |

### Container Singleton（有状态业务）

| 类 | 内部状态 |
|----|---------|
| MediaService | TmdbLookup 缓存引用 |
| TmdbClient | HTTP 响应缓存 |
| TmdbLookup | TMDB 查询结果缓存 |
| DouBan | 请求缓存 |
| Bangumi | 请求缓存 |
| Scraper | 元数据缓存 |
| Fanart | 图片元数据缓存 |
| MediaCache | 显式缓存字典 |
| WordsService | 识别词规则缓存 |
| SiteUserInfo | 站点用户信息缓存 |
| SiteConf | 站点配置缓存 |

### Container Factory（无状态）

所有 Service、Repository、Strategy、Helper 均注册为 Factory。
