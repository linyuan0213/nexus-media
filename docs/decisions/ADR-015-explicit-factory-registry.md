# ADR-015: 全面移除 DI 框架与自托管单例 — 显式工厂 + 注册表模式

## Status

Completed

## Date

2026-06-11

## Updated

2026-06-12

---

## Context

### 现状诊断

基于对 `src/` 目录的全面扫描，当前依赖管理存在三类问题：

| 问题类型 | 数量 | 影响 |
|---------|------|------|
| 自托管单例（`get_instance()`） | 11 个类 + 99 处调用 | 隐藏依赖、生命周期不可控 |
| `@inject` 注入点 | 33 个 | 框架魔法、测试困难 |
| 方法内 `get_instance()` 调用 | 65 处 | 运行时依赖不可见 |
| Service 调用 `container.xxx()` | 约 200 处 | Service Locator 反模式 |

### 具体分布

**自托管单例类（11 个）**：

| 类名 | 文件 | 被调用次数 | 问题 |
|------|------|-----------|------|
| `EventBus` | `app/events/bus.py` | 3 | 事件总线，被 Service 层直接获取 |
| `Message` | `app/message/message.py` | 3 | 消息 Facade，被多 Service 使用 |
| `SiteCache` | `app/sites/site_cache.py` | 3 | 站点缓存，被 Brush/Subscribe 获取 |
| `SyncEngine` | `app/services/sync_engine.py` | 1 | 目录同步引擎 |
| `SchedulerCore` | `app/services/scheduler/core.py` | 1 | 调度器核心 |
| `MediaServer` | `app/mediaserver/media_server.py` | 1 | 媒体服务器客户端 |
| `DownloadMonitor` | `app/services/download_monitor.py` | 1 | 下载监控 |
| `SiteEngine` | `app/sites/engine.py` | 1 | 站点定义引擎 |
| `ConfigReloader` | `app/services/config_reloader.py` | 1 | 配置重载 |
| `PluginRegistry` | `app/plugin_framework/registry.py` | 1 | 插件注册表 |
| `HookSystem` | `app/plugin_framework/hook_system.py` | 1 | 钩子系统 |

**`@inject` 注入点（33 个，31 个类）**：

`MediaService`, `APIKeyService`, `AuthService`, `BrushTaskService`, `BrushService`, `DownloadCore`, `DownloadMonitor`, `DownloadService`, `DownloaderCore`, `FileIndexService`, `FilterService`, `IndexerService`, `MediaConfigService`, `MediaFileService`, `MediaInfoService`, `MediaLibraryService`, `MediaRecommendationService`, `PluginFrameworkService`, `RssTaskService`, `SearchResultProcessor`, `SearchService`, `Searcher`, `SiteService`, `StorageBackendService`, `SubscribeService`, `SubscriptionMonitor`, `SyncService`, `SystemLifecycleService`, `TorrentRemoverRepository`, `TorrentRemoverService`, `TransferHistoryService`, `TransferPipeline`, `WordsService`

**方法内 `get_instance()` 调用（65 处，44 个类）**：

分布在 `app/services/`, `app/plugin_framework/`, `app/sites/`, `app/downloader/`, `app/indexer/` 等模块。

---

## Decision

### 核心决策

1. **完全移除 `dependency-injector`** 库及其所有用法（`@inject`, `Provide`, `wire_modules`, `DeclarativeContainer`）
2. **完全移除所有 `get_instance() / close_instance()`** 自托管单例模式
3. **所有对象由显式工厂函数创建**，按拓扑顺序组装
4. **纯字典注册表**存储运行时对象，供 `Depends` 和 lifespan 使用
5. **Service 层通过纯构造函数接收所有依赖**（包括原"单例"）
6. **底层组件同样通过构造函数接收依赖**，由上层组件传入

### 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: API Routers (api/routers/*.py)                   │
│  获取方式: FastAPI Depends                                  │
│  deps.get_sync_service() → registry.get("sync_service")     │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Service Facade (app/services/*.py)               │
│  获取方式: 纯构造函数注入                                   │
│  def __init__(self, dep1: Dep1, dep2: Dep2):               │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Business Components (app/media, app/message...)  │
│  获取方式: 纯构造函数注入                                   │
│  MessageCenter, ClientManager, EventHandlerRegistry        │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Infrastructure (app/events, app/infrastructure...)│
│  获取方式: 纯构造函数注入                                   │
│  EventBus, HttpClient, ThreadExecutor, CacheManager        │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Factories (app/di/factories.py)                  │
│  职责: 按拓扑顺序创建所有对象，组装依赖关系                 │
│  注册: registry.set("name", instance)                      │
├─────────────────────────────────────────────────────────────┤
│  Registry (app/di/registry.py)                             │
│  dict[str, Any] — 运行时对象注册表                         │
│  set() / get() / clear()                                   │
└─────────────────────────────────────────────────────────────┘
```

**关键规则**：
- **禁止**在 Service/组件/工具函数中调用 `registry.get()`
- **禁止**在方法内部调用 `get_instance()`
- **禁止**使用 `@inject` 和 `Provide`
- **禁止**在函数/方法内部使用 `import`/`from` 导入依赖
  - 所有 `import`/`from` 必须放在文件顶部
  - 如遇循环依赖，通过重构模块结构或调整 `__init__.py` 延迟导入来解除
  - 工厂函数（`factories.py`）同样需要将所有导入放在文件顶部
- **唯一**允许调用 `registry.get()` 的地方：`api/di/deps.py`（FastAPI Depends）和 `api/main.py`（lifespan）

---

## 详细设计

### 1. Registry（运行时对象注册表）

```python
# app/di/registry.py
from typing import Any


class Registry:
    """运行时对象注册表 — 纯字典，零框架依赖。

    使用位置：
    - app/di/factories.py: 创建对象后注册
    - app/di/deps.py: FastAPI Depends 获取
    - api/main.py: lifespan 中启动/关闭
    - tests/: 测试中 mock

    禁止使用位置：
    - app/services/*: Service 内部不得调用
    - app/media/*: 媒体组件内部不得调用
    - app/message/*: 消息组件内部不得调用
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def set(self, name: str, instance: Any) -> None:
        self._store[name] = instance

    def get(self, name: str) -> Any:
        if name not in self._store:
            raise KeyError(f"'{name}' 尚未注册。请在 app/di/factories.py 中创建并注册。")
        return self._store[name]

    def clear(self) -> None:
        self._store.clear()


# 全局实例 — 由 lifespan 控制生命周期
registry = Registry()
```

### 2. Factories（显式对象工厂）

```python
# app/di/factories.py
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

# Layer 1: 基础设施
from app.events.bus import EventBus
from app.events.registry import EventHandlerRegistry
from app.infrastructure.cache_system.cache_manager import CacheManager
from app.infrastructure.http.client import AsyncHttpClient, HttpClient
from app.infrastructure.queue.factory import MessageQueueFactory
from app.infrastructure.thread import ThreadExecutor

# Layer 2: 业务组件
from app.message.core.client_manager import ClientManager
from app.message.core.command_manager import CommandManager
from app.message.core.dispatcher import MessageDispatcher
from app.message.core.template_engine import TemplateEngine
from app.message.message_center import MessageCenter
from app.sites.siteconf import SiteConf
from app.sites.site_userinfo import SiteUserInfo

# Layer 3: 业务 Facade
from app.media.service import MediaService
from app.mediaserver import MediaServer
from app.message.message import Message
from app.plugin_framework.hook_system import HookSystem
from app.plugin_framework.registry import PluginRegistry
from app.plugin_framework.sandbox import PluginSandbox
from app.services.config_reloader import ConfigReloader
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache

# Layer 4: Service
from app.db.repositories.config_repo_adapter import DownloaderRepositoryAdapter
from app.db.repositories.download_repo_adapter import (
    DownloadHistoryRepositoryAdapter,
    DownloadSettingRepositoryAdapter,
)
from app.db.repositories.storage_backend_repo_adapter import StorageBackendRepositoryAdapter
from app.db.repositories.sync_repo_adapter import SyncPathRepositoryAdapter
from app.downloader.client_factory import DownloadClientFactory
from app.services.download_core import DownloadCore
from app.services.downloader_core import DownloaderCore
from app.services.filetransfer_service import FileTransferService as FileTransfer
from app.services.sync_engine import SyncEngine
from app.services.sync_service import SyncService
from app.sites import SiteConf, SiteSubtitle

# Layer 5: 协调器
from app.services.download_monitor import DownloadMonitor
from app.services.scheduler.core import SchedulerCore
from app.services.system.lifecycle import SystemLifecycleService

from app.di.registry import registry


def _build_infrastructure() -> None:
    """创建 Layer 1 基础设施。"""
    event_bus = EventBus(
        registry=EventHandlerRegistry(),
        message_queue=MessageQueueFactory.create(),
    )
    http_client = HttpClient()
    async_http = AsyncHttpClient()
    thread_executor = ThreadExecutor.named("default")
    cache_manager = CacheManager()

    registry.set("event_bus", event_bus)
    registry.set("http_client", http_client)
    registry.set("async_http_client", async_http)
    registry.set("thread_executor", thread_executor)
    registry.set("cache_manager", cache_manager)


def _build_business_components() -> None:
    """创建 Layer 2 业务组件。"""
    message_center = MessageCenter()
    client_manager = ClientManager()
    site_userinfo = SiteUserInfo()
    site_conf = SiteConf()

    registry.set("message_center", message_center)
    registry.set("client_manager", client_manager)
    registry.set("site_userinfo", site_userinfo)
    registry.set("site_conf", site_conf)


def _build_business_facades() -> None:
    """创建 Layer 3 业务 Facade（原"单例"）。"""
    # Message Facade — 组装底层组件
    client_manager = registry.get("client_manager")
    message_center = registry.get("message_center")
    command_manager = CommandManager(client_manager)
    template_engine = TemplateEngine()
    dispatcher = MessageDispatcher(client_manager, message_center)
    message = Message(
        message_center=message_center,
        client_manager=client_manager,
        command_manager=command_manager,
        template_engine=template_engine,
        dispatcher=dispatcher,
    )

    site_cache = SiteCache()
    site_engine = SiteEngine()
    config_reloader = ConfigReloader()
    plugin_registry = PluginRegistry()
    hook_system = HookSystem()
    plugin_sandbox = PluginSandbox()
    media_server = MediaServer()

    registry.set("message", message)
    registry.set("site_cache", site_cache)
    registry.set("site_engine", site_engine)
    registry.set("config_reloader", config_reloader)
    registry.set("plugin_registry", plugin_registry)
    registry.set("hook_system", hook_system)
    registry.set("plugin_sandbox", plugin_sandbox)
    registry.set("media_server", media_server)


def _build_services() -> None:
    """创建 Layer 4 Service。"""
    # DownloadCore — 原"单例"，现由工厂创建
    download_core = DownloadCore(
        client_factory=DownloadClientFactory(),
        message=registry.get("message"),
        mediaserver=registry.get("media_server"),
        event_bus=registry.get("event_bus"),
        sites=registry.get("site_cache"),
        siteconf=SiteConf(),
        sitesubtitle=SiteSubtitle(),
        filetransfer=FileTransfer(),
        download_repo=DownloadHistoryRepositoryAdapter(),
        download_setting_repo=DownloadSettingRepositoryAdapter(),
        systemconfig=registry.get("config_reloader"),  # 或专门的 SystemConfig
        downloader_repo=DownloaderRepositoryAdapter(),
    )
    registry.set("download_core", download_core)

    # SyncEngine
    sync_engine = SyncEngine(
        transfer_engine=FileTransfer(),
        sync_path_repo=SyncPathRepositoryAdapter(),
        storage_backend_repo=StorageBackendRepositoryAdapter(),
    )
    registry.set("sync_engine", sync_engine)

    # SyncService
    sync_service = SyncService(
        sync=sync_engine,
        filetransfer=FileTransfer(),
        media_cache=registry.get("media_cache"),
        thread_executor=registry.get("thread_executor"),
        storage_backend_repo=StorageBackendRepositoryAdapter(),
    )
    registry.set("sync_service", sync_service)

    # ... 其他 Service 同理


def _build_coordinators() -> None:
    """创建 Layer 5 协调器。"""
    scheduler_core = SchedulerCore()
    download_monitor = DownloadMonitor(
        client_factory=registry.get("download_core")._client_factory,  # 或传入 download_core
        event_bus=registry.get("event_bus"),
    )
    system_lifecycle = SystemLifecycleService(
        scheduler_core=scheduler_core,
        download_monitor=download_monitor,
        sync=registry.get("sync_engine"),
        # ... 其他依赖
    )

    registry.set("scheduler_core", scheduler_core)
    registry.set("download_monitor", download_monitor)
    registry.set("system_lifecycle", system_lifecycle)

    scheduler_core = SchedulerCore()
    download_monitor = DownloadMonitor(
        client_factory=registry.get("download_core")._client_factory,  # 或传入 download_core
        event_bus=registry.get("event_bus"),
    )
    system_lifecycle = SystemLifecycleService(
        scheduler_core=scheduler_core,
        download_monitor=download_monitor,
        sync=registry.get("sync_engine"),
        # ... 其他依赖
    )

    registry.set("scheduler_core", scheduler_core)
    registry.set("download_monitor", download_monitor)
    registry.set("system_lifecycle", system_lifecycle)


def build_all() -> None:
    """按拓扑顺序创建所有对象。"""
    log.info("[DI]开始构建对象图...")
    _build_infrastructure()
    _build_business_components()
    _build_business_facades()
    _build_services()
    _build_coordinators()
    log.info("[DI]对象图构建完成")
```

### 3. Deps（FastAPI Depends）

```python
# app/di/deps.py
"""FastAPI Depends 函数 — 唯一允许调用 registry.get() 的非测试文件。

职责：
- 为 API Router 提供类型化的依赖注入
- 从 Registry 获取已创建的对象
"""

from app.di.registry import registry


# ── 基础设施 ──
def get_event_bus():
    return registry.get("event_bus")


def get_thread_executor():
    return registry.get("thread_executor")


# ── Service ──
def get_sync_service():
    return registry.get("sync_service")


def get_download_core():
    return registry.get("download_core")


def get_filter_service():
    return registry.get("filter_service")


def get_site_service():
    return registry.get("site_service")
```

### 4. Service 层改造示例

#### 4.1 基础设施类改造（移除 `get_instance()`）

**改造前**：

```python
# app/events/bus.py
class EventBus:
    _instance = None

    @classmethod
    def get_instance(cls, registry=None, queue=None):
        if cls._instance is None:
            cls._instance = cls(registry=registry, queue=queue)
        return cls._instance

    @classmethod
    def close_instance(cls):
        if cls._instance:
            cls._instance.shutdown()
            cls._instance = None

    def __init__(self, registry, queue=None):
        self._registry = registry
        self._queue = queue
```

**改造后**：

```python
# app/events/bus.py
class EventBus:
    """事件总线 — 普通类，无单例逻辑。

    由 app/di/factories.py 创建一次并注册到 registry。
    Service 层通过构造函数接收。
    """

    def __init__(
        self,
        registry: EventHandlerRegistry,
        message_queue: MessageQueue | None = None,
        middleware: list[Middleware] | None = None,
        bridge: PluginBridge | None = None,
    ):
        self._registry = registry
        self._queue = message_queue
        self._middleware = middleware or []
        self._bridge = bridge
        self._running = False

    def shutdown(self) -> None:
        """关闭事件总线，释放资源。"""
        self._running = False
        if self._queue:
            self._queue.close()
```

#### 4.2 Service 类改造（移除 `@inject`）

**改造前**：

```python
# app/services/download_core.py
from dependency_injector.wiring import inject, Provide
from app.di.container import Container

class DownloadCore:
    @inject
    def __init__(
        self,
        client_factory: DownloadClientFactory = Provide[Container.download_client_factory],
        message: Message = Provide[Container.message],
        mediaserver: MediaServer = Provide[Container.media_server],
        event_bus: EventBus = Provide[Container.event_bus],
        sites=None,
    ):
        self._client_factory = client_factory
        self._message = message
        self._mediaserver = mediaserver
        self._event_bus = event_bus
        self._sites = sites or SiteCache.get_instance()  # ← 隐藏依赖
```

**改造后**：

```python
# app/services/download_core.py
class DownloadCore:
    """下载核心业务服务 — 纯构造函数注入。"""

    def __init__(
        self,
        client_factory: DownloadClientFactory,
        message: Message,
        mediaserver: MediaServer,
        event_bus: EventBus,
        sites: SiteCache,
        siteconf: SiteConf,
        sitesubtitle: SiteSubtitle,
        filetransfer: FileTransfer,
        download_repo: DownloadHistoryRepositoryAdapter,
        download_setting_repo: DownloadSettingRepositoryAdapter,
        systemconfig: SystemConfig,
        downloader_repo: DownloaderRepositoryAdapter,
    ):
        self._client_factory = client_factory
        self._message = message
        self._mediaserver = mediaserver
        self._event_bus = event_bus
        self._sites = sites
        self._siteconf = siteconf
        self._sitesubtitle = sitesubtitle
        self._filetransfer = filetransfer
        self._download_repo = download_repo
        self._download_setting_repo = download_setting_repo
        self._systemconfig = systemconfig
        self._downloader_repo = downloader_repo
        self._pipeline = DownloadPipeline(
            client_factory=self._client_factory,
            message=self._message,
            mediaserver=self._mediaserver,
        )
```

#### 4.3 底层组件改造

**改造前**：

```python
# app/message/message.py
class Message:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, message_center=None):
        self._domain = get_domain() or ""
        self.messagecenter = message_center or MessageCenter()
        self._client_manager = ClientManager()
        self._command_manager = CommandManager(self._client_manager)
        ...
```

**改造后**：

```python
# app/message/message.py
class Message:
    """消息业务 Facade — 纯构造函数注入。

    由 app/di/factories.py 组装所有底层组件后创建。
    """

    def __init__(
        self,
        message_center: MessageCenter,
        client_manager: ClientManager,
        command_manager: CommandManager,
        template_engine: TemplateEngine,
        dispatcher: MessageDispatcher,
        domain: str = "",
    ):
        self._message_center = message_center
        self._client_manager = client_manager
        self._command_manager = command_manager
        self._template_engine = template_engine
        self._dispatcher = dispatcher
        self._domain = domain
```

### 5. Lifespan 改造

```python
# api/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.di.factories import build_all
from app.di.registry import registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 显式创建、启动、关闭所有对象。"""
    # 1. 创建所有对象（按拓扑顺序）
    build_all()

    # 2. 启动业务服务
    sync_engine = registry.get("sync_engine")
    scheduler_core = registry.get("scheduler_core")
    download_monitor = registry.get("download_monitor")
    system_lifecycle = registry.get("system_lifecycle")

    sync_engine.init()
    scheduler_core.start_service(load_defaults=True)
    download_monitor.start()
    system_lifecycle.start_service()

    yield

    # 3. 反向关闭（按创建顺序的逆序）
    system_lifecycle.stop_service()
    download_monitor.stop()
    scheduler_core.stop_service()
    sync_engine.stop()

    # 4. 清理注册表
    registry.clear()
```

### 6. Router 改造

```python
# api/routers/sync.py
from fastapi import APIRouter, Depends

from app.di.deps import get_sync_service
from app.services.sync_service import SyncService

router = APIRouter()

@router.post("/sync")
async def run_sync(svc: SyncService = Depends(get_sync_service)):
    """手动执行同步。"""
    result = svc.run_sync()
    return {"success": result}
```

---

## 测试策略

### 直接构造（推荐）

```python
def test_download_core():
    """直接构造 DownloadCore，传入 mock 依赖。"""
    core = DownloadCore(
        client_factory=MockClientFactory(),
        message=MockMessage(),
        mediaserver=MockMediaServer(),
        event_bus=MockEventBus(),
        sites=MockSiteCache(),
        siteconf=MockSiteConf(),
        sitesubtitle=MockSiteSubtitle(),
        filetransfer=MockFileTransfer(),
        download_repo=MockDownloadRepo(),
        download_setting_repo=MockDownloadSettingRepo(),
        systemconfig=MockSystemConfig(),
        downloader_repo=MockDownloaderRepo(),
    )
    result = core.download(media_info=mock_media)
    assert result.success
```

### 通过 Registry mock

```python
from app.di.registry import registry


def test_with_registry():
    """通过 Registry 设置 mock 对象。"""
    registry.set("download_core", DownloadCore(...))
    core = registry.get("download_core")

    result = core.download(media_info=mock_media)
    assert result.success

    registry.clear()  # 清理
```

### conftest.py（极简）

```python
# tests/conftest.py
"""测试全局配置 — 无需 _init_container fixture。

每个测试直接构造所需对象，或按需设置 Registry。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base


@pytest.fixture(scope="session")
def engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture(scope="function")
def db_session(engine):
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
```

---

## 迁移路径

### Phase 1：创建新基础设施（1 天）

1. 新建 `app/di/registry.py` — 纯字典注册表
2. 新建 `app/di/factories.py` — 工厂函数骨架
3. 新建 `app/di/deps.py` — FastAPI Depends 函数
4. 从 `pyproject.toml` 移除 `dependency-injector`
5. 运行 `uv sync`

### Phase 2：改造基础设施类（1.5 天）

逐个移除 11 个自托管单例类的 `get_instance()` / `close_instance()`：

| 天数 | 改造类 |
|------|--------|
| 第1天上午 | EventBus, HttpClient, AsyncHttpClient, ThreadExecutor |
| 第1天下午 | SiteCache, SiteEngine, ConfigReloader |
| 第2天上午 | Message, MediaServer, DownloadMonitor |
| 第2天下午 | SchedulerCore, SyncEngine, PluginRegistry, HookSystem, PluginSandbox |

### Phase 3：改造 Service 层（3 天）

逐个移除 33 个 `@inject` 注入点：

| 天数 | 改造 Service |
|------|-------------|
| 第1天 | MediaService, DownloadCore, DownloadService, DownloaderCore, SyncService |
| 第2天 | FilterService, IndexerService, SiteService, SubscribeService, SearchService |
| 第3天 | BrushService, RssTaskService, TorrentRemoverService, TransferHistoryService, 其他 |

### Phase 4：清理方法内 `get_instance()`（2 天）

逐个清理 65 处方法内 `get_instance()` 调用，改为构造函数注入：

| 模块 | 工作量 |
|------|--------|
| `app/services/` | 15 处 |
| `app/plugin_framework/` | 20 处 |
| `app/sites/` | 20 处 |
| `app/downloader/`, `app/indexer/` | 10 处 |

### Phase 5：改造 lifespan 和 deps.py（0.5 天）

1. 修改 `api/main.py`：调用 `build_all()`
2. 修改 `api/deps.py`：使用 `registry.get()`
3. 更新所有 router

### Phase 6：测试改造（1 天）

1. 移除 `tests/conftest.py` 中的 `_init_container` fixture
2. 运行测试套件，修复失败用例
3. 为直接构造模式补充测试

### Phase 7：清理与验证（0.5 天）

1. 全局检查 `from dependency_injector` 导入
2. 全局检查 `get_instance()` 调用
3. 运行 `uv run ruff check .`
4. 运行 `uv run pyright src/ tests/`
5. 运行 `uv run pytest tests/ -v`

**总计：约 9.5 个工作日**

---

## 关键问答

### Q1: Service 构造函数参数太多怎么办？

**A**: 参数多说明依赖多，这是好事（依赖可见）。如果超过 8 个：

1. **保持显式传参**（推荐）：每个 Service 的 `__init__` 列出所有依赖
2. **拆分 Service**：参数多说明职责过重，应拆分为多个小 Service
3. **上下文对象**（可选）：将多个相关依赖封装为上下文对象

```python
# 可选：基础设施上下文
@dataclass
class InfraContext:
    event_bus: EventBus
    message: Message
    thread_executor: ThreadExecutor

class SomeService:
    def __init__(self, infra: InfraContext, business_dep: SomeDep):
        self._event_bus = infra.event_bus
```

### Q2: 深层依赖（A 依赖 B，B 依赖 C，C 依赖 D）怎么传递？

**A**: 工厂函数按拓扑顺序创建，每个对象创建时传入已创建的依赖：

```python
def build_all():
    # D → C → B → A
    d = ComponentD()
    registry.set("d", d)

    c = ComponentC(component_d=d)
    registry.set("c", c)

    b = ComponentB(component_c=c)
    registry.set("b", b)

    a = ComponentA(component_b=b)
    registry.set("a", a)
```

### Q3: Registry 是全局状态，不是又变成 Service Locator 了吗？

**A**: 关键区别在于**调用位置限制**：

| 允许调用 `registry.get()` | 禁止调用 |
|--------------------------|---------|
| `app/di/factories.py` | `app/services/*` |
| `app/di/deps.py` | `app/media/*` |
| `api/main.py` lifespan | `app/message/*` |
| `tests/*` | `app/plugin_framework/*` |

Service 层只能通过构造函数接收依赖，不接触 Registry。

### Q4: 为什么不用 `@lru_cache` 或模块级变量实现单例？

**A**: 这些方案仍然隐藏了对象创建逻辑和依赖关系。显式工厂函数让：
- 创建顺序完全可见
- 依赖关系完全可见
- 生命周期完全可控

### Q5: 如果某个 Service 只在特定路由中使用，需要全局创建吗？

**A**: 不需要。工厂函数可以按需创建：

```python
def build_all():
    # 核心 Service（全局创建）
    registry.set("sync_service", SyncService(...))

    # 按需 Service（在 deps.py 中创建）
    # def get_some_service():
    #     return SomeService(dep=registry.get("..."))
```

### Q6: 底层组件（如 MessageCenter）如何获取配置？

**A**: 配置通过构造函数传入，由工厂函数读取后传入：

```python
# 工厂函数读取配置
config = settings.get("message") or {}
message_center = MessageCenter(config=config)

# 底层组件接收配置
class MessageCenter:
    def __init__(self, config: dict):
        self._config = config
```

---

## Consequences

### 正面影响

1. **零第三方 DI 依赖**：移除 `dependency-injector`，减少外部依赖
2. **零魔法**：没有 `@inject`，没有 `wire_modules`，没有 `Provide`
3. **单例问题彻底解决**：不再使用 `get_instance()`，所有对象由工厂统一管理
4. **依赖完全可见**：通过 `__init__` 签名即可读取全部依赖
5. **测试极简**：直接 `new Service(mock)`，无需 wiring、无需 mock 占位符
6. **启动顺序完全可控**：对象创建顺序在 `factories.py` 中显式体现
7. **学习成本极低**：新开发者只需理解"构造函数传参"和"字典注册表"
8. **分层清晰**：Layer 0-4 职责明确，无越层调用

### 负面影响

1. **工厂函数手动维护**：新增 Service 需要更新 `factories.py`
2. **Service 参数可能较多**：但参数多说明依赖多，是设计反馈
3. **Registry 是全局状态**：但仅限 factories/deps/lifespan 层使用

### 缓解措施

- 工厂函数可通过 AST 工具自动生成
- 参数过多的 Service 应拆分职责
- Registry 可通过 TypedDict 或枚举增强类型安全

---

## 附录：完整改造清单

### 自托管单例类改造（11 个）

| 类名 | 文件 | 改造内容 |
|------|------|---------|
| EventBus | `app/events/bus.py` | 移除 `get_instance()` / `close_instance()` |
| Message | `app/message/message.py` | 移除 `get_instance()` / `close_instance()` |
| SiteCache | `app/sites/site_cache.py` | 移除 `get_instance()` / `close_instance()` |
| SyncEngine | `app/services/sync_engine.py` | 移除 `get_instance()` / `close_instance()` |
| SchedulerCore | `app/services/scheduler/core.py` | 移除 `get_instance()` / `close_instance()` |
| MediaServer | `app/mediaserver/media_server.py` | 移除 `get_instance()` / `close_instance()` |
| DownloadMonitor | `app/services/download_monitor.py` | 移除 `get_instance()` / `close_instance()` |
| SiteEngine | `app/sites/engine.py` | 移除 `get_instance()` / `close_instance()` |
| ConfigReloader | `app/services/config_reloader.py` | 移除 `get_instance()` / `close_instance()` |
| PluginRegistry | `app/plugin_framework/registry.py` | 移除 `get_instance()` / `close_instance()` |
| HookSystem | `app/plugin_framework/hook_system.py` | 移除 `get_instance()` / `close_instance()` |

### @inject 注入点移除（33 个）

| 类名 | 文件 | 改造内容 |
|------|------|---------|
| MediaService | `app/media/service.py` | 移除 `@inject`，改为纯构造函数 |
| APIKeyService | `app/services/apikey_service.py` | 移除 `@inject`，改为纯构造函数 |
| AuthService | `app/services/auth_service.py` | 移除 `@inject`，改为纯构造函数 |
| BrushTaskService | `app/services/brush/task_service.py` | 移除 `@inject`，改为纯构造函数 |
| BrushService | `app/services/brush_service.py` | 移除 `@inject`，改为纯构造函数 |
| DownloadCore | `app/services/download_core.py` | 移除 `@inject`，改为纯构造函数 |
| DownloadMonitor | `app/services/download_monitor.py` | 移除 `@inject`，改为纯构造函数 |
| DownloadService | `app/services/download_service.py` | 移除 `@inject`，改为纯构造函数 |
| DownloaderCore | `app/services/downloader_core.py` | 移除 `@inject`，改为纯构造函数 |
| FileIndexService | `app/services/file_index_service.py` | 移除 `@inject`，改为纯构造函数 |
| FilterService | `app/services/filter_service.py` | 移除 `@inject`，改为纯构造函数 |
| IndexerService | `app/services/indexer_service.py` | 移除 `@inject`，改为纯构造函数 |
| MediaConfigService | `app/services/media_config_service.py` | 移除 `@inject`，改为纯构造函数 |
| MediaFileService | `app/services/media_file_service.py` | 移除 `@inject`，改为纯构造函数 |
| MediaInfoService | `app/services/media_info_service.py` | 移除 `@inject`，改为纯构造函数 |
| MediaLibraryService | `app/services/media_library_service.py` | 移除 `@inject`，改为纯构造函数 |
| MediaRecommendationService | `app/services/media_recommendation_service.py` | 移除 `@inject`，改为纯构造函数 |
| PluginFrameworkService | `app/services/plugin_framework_service.py` | 移除 `@inject`，改为纯构造函数 |
| RssTaskService | `app/services/rss_automation/task_service.py` | 移除 `@inject`，改为纯构造函数 |
| SearchResultProcessor | `app/services/search_service.py` | 移除 `@inject`，改为纯构造函数 |
| SearchService | `app/services/search_service.py` | 移除 `@inject`，改为纯构造函数 |
| Searcher | `app/services/search_service.py` | 移除 `@inject`，改为纯构造函数 |
| SiteService | `app/services/site_service.py` | 移除 `@inject`，改为纯构造函数 |
| StorageBackendService | `app/services/storage_backend_service.py` | 移除 `@inject`，改为纯构造函数 |
| SubscribeService | `app/services/subscribe/management/service.py` | 移除 `@inject`，改为纯构造函数 |
| SubscriptionMonitor | `app/services/subscribe/monitor.py` | 移除 `@inject`，改为纯构造函数 |
| SyncService | `app/services/sync_service.py` | 移除 `@inject`，改为纯构造函数 |
| SystemLifecycleService | `app/services/system/lifecycle.py` | 移除 `@inject`，改为纯构造函数 |
| TorrentRemoverRepository | `app/services/torrentremover_core.py` | 移除 `@inject`，改为纯构造函数 |
| TorrentRemoverService | `app/services/torrentremover_core.py` | 移除 `@inject`，改为纯构造函数 |
| TransferHistoryService | `app/services/transfer_history_service.py` | 移除 `@inject`，改为纯构造函数 |
| TransferPipeline | `app/services/transfer_pipeline.py` | 移除 `@inject`，改为纯构造函数 |
| WordsService | `app/services/words_service.py` | 移除 `@inject`，改为纯构造函数 |

### 方法内 get_instance() 清理（65 处）

| 模块 | 数量 | 处理方式 |
|------|------|---------|
| `app/services/` | 15 | 改为构造函数注入 |
| `app/plugin_framework/` | 20 | 改为构造函数注入 |
| `app/sites/` | 20 | 改为构造函数注入 |
| `app/downloader/`, `app/indexer/` | 10 | 改为构造函数注入 |

## Completion Notes

- 2026-06-12: ADR-015 实施完成。
- 移除了 `dependency-injector` 框架与全部 `@inject`/`Provide` 用法。
- 清理了 Service、站点、插件框架、下载器、索引器、媒体、消息等模块中的 `registry.get()` 回退与 `get_instance()` 单例模式。
- `app/di/factories.py` 现在按拓扑顺序显式组装对象图；`api/deps.py` 与 `api/main.py` 是仅有的 Registry 读取入口。
- `Fanart` 不再作为顶级 Registry 对象暴露，仅在 `MediaService/Scraper` 内部使用。
- `HookSystem` 与 `PluginSandbox` 的循环依赖通过 `set_plugin_sandbox()` 显式回填解决。
- `APIKeyService` 提前到基础设施层创建并注入 `Message`/`ClientManager`/`ClientRegistry`。
- 全部校验通过：`uv run ruff check .`、`uv run pyright src/ tests/`、`uv run pytest tests/ -q`（731 passed）。
- 精简 Registry：移除了 `FANART`、`INDEXER_HELPER`、`TRANSFER_ENGINE`、`TRANSFER_PIPELINE`、`WEB_UTILS`、`TOOL_EXECUTOR` 等非必要顶级注册项，改为在 factories 中直接注入。
