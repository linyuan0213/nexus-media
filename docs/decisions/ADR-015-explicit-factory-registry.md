# ADR-015: 移除 DI 框架 — 不可变 AppContext + 分模块 Builder 模式

## Status

Accepted

## Date

2026-06-11

## Updated

2026-06-13

---

## Context

### 演进历程

本项目的依赖注入经历了三个阶段：

| 阶段 | 时间 | 方案 | 问题 |
|------|------|------|------|
| Phase 1 | 早期 | `dependency-injector` (`DeclarativeContainer` + `@inject` + `Provide`) | Service Locator 反模式，135 个文件直接调用容器，测试困难 |
| Phase 2 | 2026-06-12 | 手写 `Registry` + `factories.py` | 移除了框架魔法，但仍是运行时 Service Locator，返回 `Any`，全局可变状态 |
| Phase 3 | 2026-06-13 起 | 不可变 `AppContext` + 分模块 `Builder` | 显式对象图、类型安全、无全局可变注册表 |

### 现状诊断（Phase 1）

| 问题类型 | 数量 | 影响 |
|---------|------|------|
| 自托管单例（`get_instance()`） | 11 个类 + 99 处调用 | 隐藏依赖、生命周期不可控 |
| `@inject` 注入点 | 33 个 | 框架魔法、测试困难 |
| 方法内 `get_instance()` 调用 | 65 处 | 运行时依赖不可见 |
| Service 调用 `container.xxx()` | 约 200 处 | Service Locator 反模式 |

### Phase 2  registry 的问题

Phase 2 已彻底移除 `dependency-injector` 与 `get_instance()`，但仍存在以下结构性缺陷：

1. **运行时 Service Locator**
   - `registry.get(RegistryKey.X)` 返回 `Any`
   - 调用方不知道返回类型，重构时容易出错

2. **全局可变状态**
   - `registry = Registry()` 是模块级可变字典
   - 测试会互相污染
   - 生命周期由字典隐式持有

3. **`factories.py` 过大**
   - 单一文件组装 ~80 个对象
   - 110+ import，~800 行
   - 违反单一职责

4. **FastAPI 集成不够现代**
   - `deps.py` 需要为每个 Service 写 `get_xxx_service()`
   - 路由层依赖注入仍是字符串/枚举驱动

---

## Decision

### 核心决策

1. **完全移除 `dependency-injector`** 库及其所有用法（已完成）
2. **完全移除所有 `get_instance() / close_instance()`** 自托管单例模式（已完成）
3. **所有对象由分模块 Builder 显式创建**，按拓扑顺序组装
4. **用不可变 `AppContext` 替代 `Registry`**，作为运行时对象图的唯一持有者
5. **Service 层通过纯构造函数接收所有依赖**
6. **底层组件同样通过构造函数接收依赖**，由上层组件传入
7. **FastAPI 路由通过 `AppContext` 获取服务**，而非分散的 `get_xxx_service()`

### 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: API Routers (api/routers/*.py)                   │
│  获取方式: FastAPI Depends                                  │
│  ctx: AppContext = Depends(get_app_context)                 │
│  ctx.sync_service.run_sync()                                │
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
│  Layer 0: Builders (app/di/builders/*.py)                  │
│  职责: 按拓扑顺序创建所有对象                               │
│  infrastructure_builder.py / services_builder.py           │
│  coordinators_builder.py / context_builder.py              │
├─────────────────────────────────────────────────────────────┤
│  AppContext (app/di/context.py)                            │
│  frozen dataclass — 不可变运行时对象图                     │
│  由 lifespan 创建后挂到 app.state.context                  │
└─────────────────────────────────────────────────────────────┘
```

**关键规则**：
- **禁止**在 Service/组件/工具函数中接触 `AppContext`
- **禁止**在方法内部调用 `get_instance()`
- **禁止**使用 `@inject` 和 `Provide`
- **禁止**在函数/方法内部使用 `import`/`from` 导入依赖
  - 所有 `import`/`from` 必须放在文件顶部
  - 如遇循环依赖，通过重构模块结构或调整 `__init__.py` 延迟导入来解除
  - Builder 模块同样需要将导入放在文件顶部
- **唯一**允许接触对象图的地方：
  - `app/di/builders/`：创建对象
  - `app/di/deps.py`：FastAPI Depends 返回 `AppContext`
  - `api/main.py`：lifespan 创建并启动/关闭对象图

---

## 详细设计

### 1. AppContext（不可变运行时对象图）

```python
# app/di/context.py
from dataclasses import dataclass

from app.events.bus import EventBus
from app.infrastructure.thread import ThreadExecutor
from app.media.service import MediaService
from app.mediaserver.media_server import MediaServer
from app.message.message import Message
from app.plugin_framework.hook_system import HookSystem
from app.plugin_framework.sandbox import PluginSandbox
from app.services.downloader_core import DownloaderCore
from app.services.download_monitor import DownloadMonitor
from app.services.file_index_service import FileIndexService
from app.services.filter_service import FilterService
from app.services.indexer_service import IndexerService
from app.services.rss_automation.task_service import RssTaskService
from app.services.scheduler.core import SchedulerCore
from app.services.search_service import Searcher
from app.services.subscribe.monitor import SubscriptionMonitor
from app.services.subscribe_service import SubscribeService
from app.services.sync_engine import SyncEngine
from app.services.sync_service import SyncService
from app.services.system.lifecycle import SystemLifecycleService
from app.services.torrentremover_core import TorrentRemoverService
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache


@dataclass(frozen=True)
class AppContext:
    """不可变应用上下文 — 运行时对象图的唯一持有者。

    由 lifespan 创建后挂到 app.state.context，
    路由层通过 Depends(get_app_context) 获取。
    """

    # 基础设施
    event_bus: EventBus
    thread_executor: ThreadExecutor
    scheduler_core: SchedulerCore
    message: Message
    site_cache: SiteCache
    site_engine: SiteEngine
    hook_system: HookSystem
    plugin_sandbox: PluginSandbox
    media_server: MediaServer

    # 业务 Service
    media_service: MediaService
    downloader_core: DownloaderCore
    indexer_service: IndexerService
    subscribe_service: SubscribeService
    searcher: Searcher
    sync_service: SyncService
    sync_engine: SyncEngine
    rss_task_service: RssTaskService
    download_monitor: DownloadMonitor
    file_index_service: FileIndexService
    filter_service: FilterService
    torrent_remover_service: TorrentRemoverService
    subscription_monitor: SubscriptionMonitor

    # 协调器
    lifecycle: SystemLifecycleService
```

### 2. 分模块 Builder

```python
# app/di/builders/infrastructure_builder.py
from app.events.bus import EventBus
from app.events.registry import EventHandlerRegistry
from app.infrastructure.queue.factory import MessageQueueFactory
from app.infrastructure.thread import ThreadExecutor
from app.message.message import Message
from app.plugin_framework.hook_system import HookSystem
from app.plugin_framework.registry import PluginRegistry
from app.plugin_framework.sandbox import PluginSandbox
from app.services.apikey_service import APIKeyService
from app.services.scheduler.core import SchedulerCore
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache

from app.di.models import InfrastructureObjects


def build_infrastructure() -> InfrastructureObjects:
    """创建 Layer 1 基础设施对象。"""
    plugin_registry = PluginRegistry()
    thread_executor = ThreadExecutor.named("default")
    scheduler_core = SchedulerCore()
    apikey_service = APIKeyService(
        key_repo=APIKeyRepositoryAdapter(),
        log_repo=APIKeyLogRepositoryAdapter(),
    )
    message = Message(apikey_service=apikey_service)

    site_engine = SiteEngine()
    from app.sites.siteuserinfo.config_api import _api_factory
    from app.sites.siteuserinfo.config_html import _html_config_factory
    site_engine.register_user_info_factory(_api_factory)
    site_engine.register_user_info_factory(_html_config_factory)

    site_cache = SiteCache(site_engine=site_engine)
    message_queue = MessageQueueFactory.create()
    hook_system = HookSystem(plugin_sandbox=None)

    plugin_sandbox = PluginSandbox(
        plugin_registry=plugin_registry,
        message=message,
        scheduler_core=scheduler_core,
        hook_system=hook_system,
        site_engine=site_engine,
        media_service=None,  # 回填
        plugin_log_repo=PluginLogRepositoryAdapter(),
    )
    hook_system.set_plugin_sandbox(plugin_sandbox)

    event_bus = EventBus(
        registry=EventHandlerRegistry(),
        bridge=PluginBridge(hook_system=hook_system),
    )

    return InfrastructureObjects(
        event_bus=event_bus,
        thread_executor=thread_executor,
        scheduler_core=scheduler_core,
        message=message,
        site_cache=site_cache,
        site_engine=site_engine,
        hook_system=hook_system,
        plugin_sandbox=plugin_sandbox,
    )
```

```python
# app/di/builders/services_builder.py
from app.di.models import BusinessFacades, InfrastructureObjects, ServiceObjects


def build_business_facades(infra: InfrastructureObjects) -> BusinessFacades:
    """创建 Layer 3 业务 Facade。"""
    media_service = MediaService(
        tmdb_lookup=TmdbLookup(),
        llm_parser=LLMParser(recognizer=...),
    )
    media_server = MediaServer(
        media_service=media_service,
        message=infra.message,
        message_queue=...,
    )
    return BusinessFacades(
        media_service=media_service,
        media_server=media_server,
    )


def build_services(
    infra: InfrastructureObjects,
    facades: BusinessFacades,
) -> ServiceObjects:
    """创建 Layer 4 业务 Service。"""
    downloader_core = build_downloader_core(infra, facades)
    sync_engine = build_sync_engine(infra, facades)
    sync_service = SyncService(
        sync=sync_engine,
        filetransfer=...,
        media_cache=MediaCache(),
        thread_executor=infra.thread_executor,
        storage_backend_repo=StorageBackendRepositoryAdapter(),
    )
    # ... 其他 Service
    return ServiceObjects(
        downloader_core=downloader_core,
        sync_service=sync_service,
        sync_engine=sync_engine,
        # ...
    )
```

```python
# app/di/builders/context_builder.py
from app.di.builders.infrastructure_builder import build_infrastructure
from app.di.builders.services_builder import build_business_facades, build_services
from app.di.builders.coordinators_builder import build_coordinators
from app.di.context import AppContext


def build_app_context() -> AppContext:
    """按拓扑顺序组装整个应用对象图。"""
    infra = build_infrastructure()
    facades = build_business_facades(infra)
    services = build_services(infra, facades)
    coordinators = build_coordinators(infra, facades, services)

    return AppContext(
        event_bus=infra.event_bus,
        thread_executor=infra.thread_executor,
        scheduler_core=infra.scheduler_core,
        message=infra.message,
        site_cache=infra.site_cache,
        site_engine=infra.site_engine,
        hook_system=infra.hook_system,
        plugin_sandbox=infra.plugin_sandbox,
        media_server=facades.media_server,
        media_service=facades.media_service,
        downloader_core=services.downloader_core,
        indexer_service=services.indexer_service,
        subscribe_service=services.subscribe_service,
        searcher=services.searcher,
        sync_service=services.sync_service,
        sync_engine=services.sync_engine,
        rss_task_service=services.rss_task_service,
        download_monitor=services.download_monitor,
        file_index_service=services.file_index_service,
        filter_service=services.filter_service,
        torrent_remover_service=services.torrent_remover_service,
        subscription_monitor=coordinators.subscription_monitor,
        lifecycle=coordinators.lifecycle,
    )
```

### 3. Deps（FastAPI Depends）

```python
# app/di/deps.py
from fastapi import Request

from app.di.context import AppContext


def get_app_context(request: Request) -> AppContext:
    """获取应用上下文 — 唯一允许在路由层使用的依赖入口。"""
    return request.app.state.context
```

### 4. Lifespan

```python
# api/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.di.builders.context_builder import build_app_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 显式创建、启动、关闭所有对象。"""
    context = build_app_context()
    app.state.context = context

    context.lifecycle.start_service()

    yield

    context.lifecycle.stop_service()
```

### 5. Router 改造

```python
# api/routers/sync.py
from fastapi import APIRouter, Depends

from app.di.context import AppContext
from app.di.deps import get_app_context

router = APIRouter()


@router.post("/sync")
async def run_sync(ctx: AppContext = Depends(get_app_context)):
    """手动执行同步。"""
    result = ctx.sync_service.run_sync()
    return {"success": result}
```

### 6. 插件集成

插件通过 `PluginContext` 接收受限能力，不接触 `AppContext`：

```python
@dataclass(frozen=True)
class PluginContext:
    """插件可见的系统能力子集。"""

    plugin_id: str
    plugin_name: str
    message: Message
    scheduler_core: SchedulerCore
    hook_system: HookSystem
    site_engine: SiteEngine
    media_service: MediaService
    event_bus: EventBus


class PluginSandbox:
    def __init__(self, app_context: AppContext, ...):
        self._app_context = app_context

    def _create_plugin_context(self, plugin_id: str) -> PluginContext:
        return PluginContext(
            plugin_id=plugin_id,
            plugin_name=...,
            message=self._app_context.message,
            scheduler_core=self._app_context.scheduler_core,
            hook_system=self._app_context.hook_system,
            site_engine=self._app_context.site_engine,
            media_service=self._app_context.media_service,
            event_bus=self._app_context.event_bus,
        )
```

---

## 测试策略

### 直接构造（推荐）

```python
def test_download_core():
    core = DownloadCore(
        client_factory=MockClientFactory(),
        message=MockMessage(),
        mediaserver=MockMediaServer(),
        event_bus=MockEventBus(),
        sites=MockSiteCache(),
        # ...
    )
    result = core.download(media_info=mock_media)
    assert result.success
```

### 构造最小 AppContext

```python
from app.di.context import AppContext


def test_with_minimal_context():
    ctx = AppContext(
        event_bus=MockEventBus(),
        thread_executor=MockThreadExecutor(),
        # ... 只填需要的字段
    )
    ctx.sync_service.run_sync()
```

### conftest.py

```python
# tests/conftest.py
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

## 迁移路径（从当前 Registry 到 AppContext）

### Phase 1：定义 AppContext 与 Builder 骨架（1 天）

1. 新建 `app/di/context.py` — `AppContext` frozen dataclass
2. 新建 `app/di/models.py` — `InfrastructureObjects`、`BusinessFacades`、`ServiceObjects`、`CoordinatorObjects`
3. 新建 `app/di/builders/` 目录：
   - `infrastructure_builder.py`
   - `services_builder.py`
   - `coordinators_builder.py`
   - `context_builder.py`
4. 将 `app/di/factories.py` 的逻辑按层拆入对应 builder

### Phase 2：迁移基础设施层（1 天）

- 把 `EventBus`、`ThreadExecutor`、`SchedulerCore`、`Message`、`SiteCache`、`SiteEngine`、`PluginSandbox`、`HookSystem` 的创建移入 `infrastructure_builder.py`
- 保持注册到 `registry` 以兼容现有路由

### Phase 3：迁移业务 Service 层（2 天）

- 把 `DownloaderCore`、`SyncService`、`SyncEngine`、`IndexerService`、`SubscribeService`、`Searcher`、`RssTaskService` 等创建移入 `services_builder.py`
- 保持注册到 `registry`

### Phase 4：迁移协调器层（1 天）

- 把 `SubscriptionMonitor`、`SystemLifecycleService` 创建移入 `coordinators_builder.py`
- `context_builder.py` 组装完整 `AppContext`

### Phase 5：接入 FastAPI（1 天）

1. `api/main.py` lifespan 改为 `context = build_app_context()` 并挂到 `app.state.context`
2. `app/di/deps.py` 提供 `get_app_context(request: Request) -> AppContext`
3. 逐步将路由从 `Depends(get_xxx_service)` 改为 `Depends(get_app_context)`

### Phase 6：移除 Registry（2 天）

1. 所有路由改用 `AppContext` 后，删除 `registry.set()` 调用
2. 删除 `app/di/registry.py` 和 `app/di/types.py`
3. 删除 `app/di/factories.py`
4. 更新测试，不再 mock registry

### Phase 7：验证（0.5 天）

1. `uv run ruff check .`
2. `uv run pyright src/ tests/`
3. `uv run pytest tests/ -v`

**总计：约 8.5 个工作日**

---

## 关键问答

### Q1: Service 构造函数参数太多怎么办？

**A**: 参数多说明依赖多，是设计反馈。如果超过 8 个：

1. **拆分 Service**：职责过重时应拆分
2. **局部上下文对象**：将同一层的一组依赖封装为 dataclass

```python
@dataclass(frozen=True)
class TransferContext:
    filetransfer: FileTransferService
    sync_engine: SyncEngine
    storage_backend_repo: StorageBackendRepositoryAdapter
```

### Q2: 深层依赖怎么传递？

**A**: Builder 按拓扑顺序创建，每个对象创建时传入已创建的依赖：

```python
def build_app_context():
    infra = build_infrastructure()       # Layer 1
    facades = build_business_facades(infra)  # Layer 3
    services = build_services(infra, facades)  # Layer 4
    coordinators = build_coordinators(infra, facades, services)  # Layer 5
    return AppContext(...)
```

### Q3: 插件如何获取单例？

**A**: 插件通过 `PluginContext` 接收受限能力，由 `PluginSandbox` 从 `AppContext` 注入。插件代码不接触 `AppContext`。

### Q4: 如果某个 Service 只在特定路由中使用，需要全局创建吗？

**A**: 轻量级 Service 可以在 Builder 中创建；真正按需的可以在路由中直接构造。`AppContext` 只持有全局单例和重量级服务。

---

## Consequences

### 正面影响

1. **零第三方 DI 依赖**：移除 `dependency-injector`
2. **零魔法**：没有 `@inject`/`Provide`
3. **类型安全**：`AppContext` 每个字段都有具体类型
4. **IDE 友好**：可跳转、可重构
5. **不可变对象图**：`frozen=True`，测试不会互相污染
6. **生命周期显式**：对象创建顺序在 Builder 中完全可见
7. **分层清晰**：每个 Builder 只负责一层
8. **插件边界清晰**：通过 `PluginContext` 注入受限能力

### 负面影响

1. **初始迁移工作量**：需要拆分 `factories.py` 并更新路由
2. **`AppContext` 字段较多**：80+ 服务会导致 dataclass 字段多
3. **路由层需要接触完整上下文**：比以前 `get_xxx_service()` 更粗粒度

### 缓解措施

- 使用 `@dataclass(frozen=True)` 自动生成 `__init__`
- 在 `AppContext` 中按层分组子上下文：

```python
@dataclass(frozen=True)
class AppContext:
    infra: InfrastructureContext
    services: ServicesContext
    coordinators: CoordinatorsContext
```

- 路由层可以通过 `ctx.services.sync_service` 访问

---

## 附录：与 Phase 2 Registry 的对比

| 维度 | Phase 2 Registry | Phase 3 AppContext + Builder |
|------|------------------|------------------------------|
| 全局可变状态 | 是 | 否 |
| 类型安全 | `Any` | 具体类型 |
| IDE 支持 | 差 | 好 |
| 文件职责 | `factories.py` 800+ 行 | 分模块 Builder |
| 路由依赖 | 多个 `get_xxx_service()` | 一个 `get_app_context()` |
| 插件访问 | 通过 registry 或注入 | 通过 `PluginContext` |
| 大厂通用性 | 低 | 高 |

---

## Completion Notes

- 2026-06-12: Phase 2 完成。移除了 `dependency-injector`、自托管单例、`@inject`/`Provide`。
- 2026-06-13: Phase 3 启动。定义不可变 `AppContext` + 分模块 Builder 作为目标架构。
- 当前校验通过：`uv run ruff check .`、`uv run pyright src/ tests/`、`uv run pytest tests/ -q`。
