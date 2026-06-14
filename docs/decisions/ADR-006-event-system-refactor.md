# ADR-006: 事件驱动模块重构方案

## Status

Accepted / Implemented

## Date

2026-05-30（决策）/ 2026-06-01（部分实施）

## Context

### 重构前的问题

1. **全局可变单例**：`EventHandler = EventManager()` 作为模块级全局变量，不可测试、不可 Mock
2. **无类型安全**：事件数据为裸 `dict`，生产者和消费者之间无结构契约
3. **同步阻塞**：`send_event` 为同步串行执行，一个 Handler 阻塞会拖慢所有后续 Handler 和调用方
4. **职责混合**：`EventManager` 同时管理本地 Handler 注册和 Plugin HookSystem 转发

### 当前实际状况

新事件系统（`app/events/`）已全面落地，发布端和消费端均已打通。

**发布端现状**：
- 已全面迁移到 `EventBus.publish(Event(...))`，约 15+ 处调用
- Payload 已定义类型化 dataclass（`app/events/payloads.py`）

**消费端现状**：
- `@on_event` 装饰器已全面使用，共 5 个 handler 模块：
  - `subscribe/handlers.py` — 4 个 handler
  - `transfer/handlers.py` — 3 个 handler
  - `download/handlers.py` — 2 个 handler
  - `search/handlers.py` — 1 个 handler
  - `system/handlers.py` — 3 个 handler
- 已消除手动 `event_bus.subscribe()` 注册
- 消费者通过 `register_modules()` 显式注册，避免隐式导入和运行时扫描

**注册机制**：
- `app/events/config.py` 集中声明 `EVENT_HANDLER_MODULES` 列表
- `app/events/decorators.py` 提供 `register_modules()` 显式导入
- `initializer.py` 中 `init_event_handlers()` 统一调用注册

---

## 目标

- 解耦事件生产者和消费者
- 引入类型安全的事件负载（dataclass）
- 支持同步+异步两种投递模式
- 统一事件注册入口，消除全局单例
- 提供中间件扩展点
- **消费者应能通过声明式方式订阅事件，无需手动注册和解析 payload**

---

## 方案设计

### 架构图

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Producer   │────▶│  EventBus    │────▶│  Middleware  │
│  (Service)   │     │              │     │   Chain      │
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                          ┌────────────────────────┼────────────────────────┐
                          ▼                        ▼                        ▼
                   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
                   │ LocalHandler │        │ HookSystem   │        │    DLQ       │
                   │  (Consumer)  │        │  (Plugin)    │        │  (Retry)     │
                   └──────────────┘        └──────────────┘        └──────────────┘
```

### 目录结构

```
src/app/events/
├── __init__.py          # export Event, EventBus, on_event, auto_register
├── types.py             # Event dataclass
├── bus.py               # EventBus：同步执行 + 异步队列投递
├── registry.py          # EventHandlerRegistry：按 event_type + priority 管理 handlers
├── middleware.py        # MiddlewareChain + LoggingMiddleware + ErrorHandlingMiddleware
└── decorators.py        # @on_event 装饰器 + _subscribers 注册表

业务 Payload 放在各业务模块（如 app/services/transfer/events.py）
```

### 核心设计决策

#### 1. 事件命名规范

统一采用 `domain.action` 格式，下划线连接多词：

```python
# 正确
"media.transfer_finished"
"media.episode_transferred"
"site.cookie_sync"

# 错误（不要混用点号和驼峰）
"media.transfer.finished"
"media.episodeTransferred"
```

#### 2. 插件桥接：零映射，直接转发

**旧方案的问题**：bridge 维护硬编码映射表，新增事件需要改核心代码。

**新方案**：
- EventBus 的事件类型直接作为 HookSystem 的 hook name
- 删除 HookSystem 的 EVENTS 白名单限制
- 插件通过 `HookSystem().on("my_plugin.custom_event", handler)` 自由注册
- bridge 只做一件事：将 Event 的 payload 序列化后调用 `HookSystem().emit()`

```python
class PluginBridge:
    def forward(self, event: Event) -> None:
        payload = event.payload.__dict__ if hasattr(event.payload, "__dict__") else event.payload
        HookSystem().emit(event.event_type, payload)
```

#### 3. EventBus：同步 + 异步统一

```python
class EventBus:
    def __init__(
        self,
        registry: EventHandlerRegistry,
        message_queue: MessageQueue | None = None,
        middleware: list[Middleware] | None = None,
        async_event_types: set[str] | None = None,
    ):
        ...

    def publish(self, event: Event) -> None:
        handlers = self._registry.get_handlers(event.event_type)
        if not handlers and event.event_type not in self._async_types:
            return

        def _execute():
            # 1. 执行本地 handlers（同步）
            if handlers:
                chain = MiddlewareChain(self._middleware, lambda e: [h(e) for h in handlers])
                chain.execute(event)
            # 2. 转发到插件（无论是否有本地 handler）
            self._bridge.forward(event)

        if event.event_type in self._async_types and self._queue:
            self._queue.submit(_execute, name=f"event:{event.event_type}")
        else:
            _execute()
```

**关键点**：
- 同步事件：调用方阻塞等待 handlers 完成（适合转移后更新数据库等关键操作）
- 异步事件：通过 `MessageQueue` 投递，调用方立即返回（适合通知、日志等非关键操作）
- 插件转发**始终执行**，不依赖是否有本地 handler

#### 4. Handler 注册：装饰器 + 自动扫描

**当前问题**：`@on_event` 装饰器已存在但零使用，消费者仍需手动 `event_bus.subscribe()` 注册。

**目标用法**：

```python
# app/services/subscribe/handlers.py
from app.events import on_event, Event
from app.events.constants import MEDIA_EPISODE_TRANSFERRED

@on_event(MEDIA_EPISODE_TRANSFERRED, priority=10)
def update_subscribe_progress(event: Event) -> None:
    payload = event.payload
    # payload 是 EpisodeTransferredPayload dataclass
    ...

# app/initializer.py
from app.events import auto_register

def init_event_handlers():
    bus = container.event_bus()
    auto_register(bus)
```

### DI 容器集成

```python
# app/di/builders/infrastructure_builder.py
def build_infrastructure() -> InfrastructureObjects:
    ...
    event_bus = EventBus(
        registry=EventHandlerRegistry(),
        bridge=PluginBridge(hook_system=hook_system),
        message_queue=message_queue,
        middleware=[
            LoggingMiddleware(),
            ErrorHandlingMiddleware(),
        ],
    )
    register_modules(EVENT_HANDLER_MODULES)
    auto_register(event_bus)
    ...
```

注意：`async_event_types` 当前未配置，所有事件默认同步执行。如需将通知类事件改为异步投递，可在创建 EventBus 时传入 `async_event_types` 集合。

### 调用方改造示例

```python
# 改造前
self.eventmanager.send_event(
    EventType.TransferFinished,
    {"media_info": media.to_dict(), "path": dest_path},
)

# 改造后
from dataclasses import dataclass
from app.events import Event
from app.events.constants import MEDIA_TRANSFER_FINISHED

@dataclass(frozen=True)
class TransferFinishedPayload:
    media_info: dict
    path: str

self._event_bus.publish(Event(
    event_type=MEDIA_TRANSFER_FINISHED,
    payload=TransferFinishedPayload(
        media_info=media.to_dict(),
        path=dest_path,
    ),
))
```

### 插件注册新事件示例

```python
# 插件代码（无需修改核心）
from app.plugin_framework.hook_system import HookSystem

# 注册自定义事件
HookSystem().on("my_plugin.custom_event", my_handler)

# 业务代码发送自定义事件
from app.events import Event

event_bus.publish(Event(
    event_type="my_plugin.custom_event",
    payload={"key": "value"},
))
```

---

## 实施记录

### Phase 1：基础设施搭建（已完成）

- **新建 `app/events/` 包**：types, bus, registry, middleware, decorators, bridge
- **删除旧代码**：EventManager, EventType, event_compat.py
- **DI Container**：`app/di/builders/infrastructure_builder.py` 创建 EventBus，注册 middleware，并显式调用 `register_modules()` + `auto_register()` 注册所有 `@on_event` handler
- **生命周期集成**：`SystemLifecycleService` 从 DI 接收真实 EventBus 实例，`init_event_handlers()` 只做缓存事件桥接 (`init_event_bridge`)

### Phase 2：发布端迁移（已完成）

约 15+ 处 `send_event` 调用已迁移到 `EventBus.publish()`：
- `subscribe/management/finish_service.py` — `SUBSCRIBE_FINISHED`
- `subscribe/management/add_service.py` — `DOWNLOAD_SUBSCRIBE_SUCCESS`
- `subscribe/management/update_service.py` — `DOWNLOAD_SUBSCRIBE_SUCCESS`
- `transfer/filetransfer_service.py` — `MEDIA_TRANSFER_FINISHED`, `MEDIA_EPISODE_TRANSFERRED`, `SUBTITLE_DOWNLOAD`, `TRANSFER_FAIL`
- `downloader/pipeline.py` — `DOWNLOAD_STARTED`, `DOWNLOAD_FAILED`, `DOWNLOAD_FINISHED`
- `search_service.py` — `DOWNLOAD_FINISHED`
- `rss_automation/executor.py` — `DOWNLOAD_SUBSCRIBE_SUCCESS`
- `media_file_service.py` — `SUBTITLE_DOWNLOAD`
- `transfer/cleanup_service.py` — `TRANSFER_FAIL`
- `system/message.py` — `DOWNLOAD_FINISHED`
- `infrastructure/cache_system/events.py` — `CACHE_EVENT`

### Phase 3：消费端落地（已完成）

1. **Payload 类型化**：新建 `app/events/payloads.py`，定义全部事件的 dataclass
   - `MediaTransferFinishedPayload`, `MediaEpisodeTransferredPayload`
   - `DownloadStartedPayload`, `DownloadFailedPayload`
   - `SubscribeFinishedPayload`, `SubscribeAddPayload`, `RssAutoSubscribeRequestedPayload`
   - `SearchStartPayload`, `SubtitleDownloadPayload`, `TransferFailPayload`
   - `MessageIncomingPayload`, `MediaSourceDeletedPayload`, `LibraryFileDeletedPayload`

2. **提取独立 Handler**：5 个 handler 文件，13 个消费者
   | 文件 | Handler 数 | 事件 |
   |------|-----------|------|
   | `subscribe/handlers.py` | 4 | SUBSCRIBE_FINISHED, SUBSCRIBE_ADD, RSS_AUTO_SUBSCRIBE_REQUESTED, MEDIA_EPISODE_TRANSFERRED |
   | `transfer/handlers.py` | 4 | MEDIA_TRANSFER_FINISHED, SUBTITLE_DOWNLOAD, TRANSFER_FAIL, DOWNLOAD_COMPLETED |
   | `download/handlers.py` | 2 | DOWNLOAD_STARTED, DOWNLOAD_FAILED |
   | `search/handlers.py` | 1 | SEARCH_START |
   | `system/handlers.py` | 3 | MESSAGE_INCOMING, MEDIA_SOURCE_DELETED, LIBRARY_FILE_DELETED |

3. **消费者注册机制**：集中式显式注册表
   - `app/events/config.py` — `EVENT_HANDLER_MODULES` 列表
   - `app/events/decorators.py` — `register_modules()` 显式导入
   - `initializer.py` — `init_event_handlers()` 统一调用

4. **消除手动 `event_bus.subscribe()` 调用**：
   - 删除 `SubscribeService._register_event_handlers()` 和 `_handle_rss_auto_subscribe()`
   - RSS_AUTO_SUBSCRIBE_REQUESTED 处理逻辑迁移到 `subscribe/handlers.py`
   - 例外：`transfer/handlers.py` 的 `handle_download_completed` 需要注入 `TransferPipeline`，保留 `register_download_completed_handler()` 显式注册，由 `services_builder` 在创建 pipeline 后调用

### Phase 4：下载完成事件驱动转移（已完成）

1. **新建 `DownloadMonitor` 服务**（`app/services/download_monitor.py`）
   - ThreadPoolExecutor 并发检查多个下载器
   - 30 秒高频轮询，检测下载器中的新完成任务
   - 发布 `download.completed` 事件
   - 预热机制避免启动时大量触发
   - `_processed_ids` 去重，防止重复处理

2. **添加 `DownloadCompletedPayload`** 到 `app/events/payloads.py`

3. **添加 `handle_download_completed` handler**（`transfer/handlers.py`）
   - 接收 `download.completed` 事件
   - 获取下载器配置（operation, post_process）
   - 构建 `TransferTask` 调用 `TransferPipeline.process()`
   - 支持 move/link/copy 模式的后处理（删种/标记状态）

4. **修改 `TransferCoordinator`**（低频兜底）
   - `PT_TRANSFER_INTERVAL`：300 秒 → 30 秒（DownloadMonitor 轮询间隔）
   - 新增 `PT_TRANSFER_INTERVAL_FALLBACK`：1800 秒（30 分钟，pttransfer 兜底扫描）
   - 兜底扫描处理因系统重启/事件丢失而未被转移的任务

5. **生命周期集成**
   - DI Container 注册 `download_monitor` provider
   - `SystemLifecycleService.start_service()` 启动 DownloadMonitor
   - `SystemLifecycleService.stop_service()` 优雅停止 DownloadMonitor
   - 删除 `SubscribeService._register_event_handlers()` 和 `_handle_rss_auto_subscribe()`
   - RSS_AUTO_SUBSCRIBE_REQUESTED 处理逻辑迁移到 `subscribe/handlers.py`

---

## Decision

全部实施完成。事件系统从全局单例迁移到 DI 驱动的声明式事件总线：

- 发布端：裸 dict payload → 类型化 dataclass payload
- 消费者：手动 `event_bus.subscribe()` → `@on_event` 装饰器 + 集中式注册表
- 注册机制：隐式导入/文件扫描 → `EVENT_HANDLER_MODULES` 显式配置

---

## Consequences

### 正面影响

- **发布端已解耦**：不再依赖全局单例，通过 DI 获取 EventBus
- **事件命名统一**：采用 `domain.action` 格式，避免旧 `EventType` 枚举膨胀
- **插件桥接简化**：零映射直接转发，新增事件无需改核心代码
- **同步/异步分离**：关键事件同步执行，非关键事件异步投递

### 负面影响

- **发布端 payload 仍为裸 dict**：dataclass 已定义但发布端尚未全面替换，消费者侧通过 `**event.payload` 解包使用

### 待验证检查清单

```bash
# 1. 检查 @on_event 使用情况
grep -r "@on_event" src/app/services/ --include="*.py" | grep -v "def on_event" | wc -l

# 2. 检查注册表完整性
cat src/app/events/config.py

# 3. 检查手动 event_bus.subscribe()（应为 0）
grep -r "\.subscribe(" src/app/services/ --include="*.py" | grep -v "registry.subscribe\|bus.subscribe"

# 4. 检查事件消费者覆盖率
grep -r "publish(" src/app/services/ --include="*.py" | wc -l  # 发布数
grep -r "@on_event" src/app/services/ --include="*.py" | wc -l  # 消费数
```
