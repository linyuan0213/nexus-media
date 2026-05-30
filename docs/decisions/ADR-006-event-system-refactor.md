# ADR-006: 事件驱动模块重构方案（修订版）

## Status
Proposed

## Date
2026-05-30

## Context

当前事件系统存在以下结构性问题：

1. **全局可变单例**：`EventHandler = EventManager()` 作为模块级全局变量，不可测试、不可 Mock
2. **无类型安全**：事件数据为裸 `dict`，生产者和消费者之间无结构契约
3. **同步阻塞**：`send_event` 为同步串行执行，一个 Handler 阻塞会拖慢所有后续 Handler 和调用方
4. **职责混合**：`EventManager` 同时管理本地 Handler 注册和 Plugin HookSystem 转发
5. **事件类型膨胀**：`EventType` 枚举集中了所有业务事件，违反开闭原则
6. **无中间件机制**：无法统一添加日志、鉴权、速率限制等横切逻辑
7. **错误隔离弱**：单个 Handler 抛异常仅打印日志，无死信队列或重试机制
8. **插件扩展难**：新增事件需要修改 `EventType` 枚举和 bridge 映射表

## 目标

- 解耦事件生产者和消费者
- 引入类型安全的事件负载（dataclass）
- 支持同步+异步两种投递模式
- 统一事件注册入口，消除全局单例
- 提供中间件扩展点
- **插件可自由注册新事件，无需修改核心代码**

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
# app/di/container.py
def event_bus(self) -> EventBus:
    from app.events import EventBus, EventHandlerRegistry
    from app.events.middleware import LoggingMiddleware, ErrorHandlingMiddleware
    from app.events.bridge import PluginBridge
    from app.infrastructure.queue.factory import MessageQueueFactory

    registry = EventHandlerRegistry()
    queue = MessageQueueFactory.create(max_workers=4)

    bus = EventBus(
        registry=registry,
        message_queue=queue,
        middleware=[
            LoggingMiddleware(),
            ErrorHandlingMiddleware(),
        ],
        async_event_types={
            "media.transfer_finished",
            "media.episode_transferred",
            "subscribe.finished",
            "message.incoming",
        },
        bridge=PluginBridge(),
    )
    return bus
```

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

## 实施步骤

1. **修改 HookSystem**：删除 EVENTS 白名单限制，允许任意事件名
2. **创建 `app/events/` 包**：types, bus, registry, middleware, decorators, bridge
3. **修改 DI Container**：提供 EventBus
4. **创建业务 Payload**：分散在各业务模块
5. **逐个修改调用方**：21 个 send_event 调用点
6. **重写消费者**：提取 EpisodeTransferredHandler，使用 @on_event
7. **修改 initializer.py**：auto_register(event_bus)
8. **删除旧代码**：EventManager, EventType, event_compat.py
9. **运行 ruff + pyright + tests**

## Decision

等待 review 后实施。
