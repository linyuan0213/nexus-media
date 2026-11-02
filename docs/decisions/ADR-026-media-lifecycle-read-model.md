# ADR-026: 媒体生命周期读模型与流转页面

## Status

Proposed

## Date

2026-11-02

## Context

下载、转移、刮削已经拆成持久队列，异步阶段变多，但状态仍分散在各领域：

| 模块 | 当前状态模型 | 位置 |
|---|---|---|
| 任务队列 | `TaskStatus` 枚举 | `src/app/infrastructure/task_queue/models.py` |
| 下载器 | `TorrentStatus` 枚举 | `src/app/schemas/download.py` |
| 下载历史 | 自由字符串 `STATE` | `DOWNLOAD_HISTORY.STATE` |
| 转移历史 | 无总状态，只有源/目标存在性 | `TRANSFER_HISTORY.SOURCE_STATE/DEST_STATE` |
| 未知转移 | `Y/N` 字符串 | `TRANSFER_UNKNOWN.STATE` |
| 同步历史 | 无状态 | `SYNC_HISTORY` |
| 刮削 | 只复用队列 `TaskStatus` | `ScrapeQueueService` |
| 订阅 | 单字母 `SubscribeState` | `D/S/R/C/E/N` |
| 重命名任务 | 独立字符串状态 | `planned/running/completed/cancelled/interrupted` |
| 入库 | 实时判断，无持久化状态 | `LibraryPresenceService` |

这会导致：

1. 同一个“失败”在下载、转移、订阅里语义不同；
2. 队列任务 ACK 后，刮削状态可能没有长期记录；
3. 无法回答“这部电影/这一集现在卡在哪一步”；
4. 无法统一统计各阶段耗时、失败率和重试次数；
5. 页面需要同时拼接下载、转移、同步、订阅、媒体服务器多个来源，仍然不可靠。

## Decision

新增一套**只读生命周期读模型（read model）**，不替换现有领域状态，也不让生命周期服务参与业务决策。

```text
领域状态 / 事件 / 历史表
        ↓ 映射
LifecycleProjector（唯一写入者）
        ↓
MEDIA_LIFECYCLE（当前状态）
MEDIA_LIFECYCLE_EVENT（时间线）
        ↓
只读 API + 流转页面
```

核心原则：

1. **领域状态仍是业务事实源**：下载器、订阅、转移、刮削继续使用自己的状态。
2. **生命周期是投影**：只做观测和展示，不阻止或驱动下载/转移/刮削。
3. **页面操作只调用原业务服务**：重试、取消、手动识别仍走现有入口。
4. **一个 projector 写入**：其他模块禁止直接写生命周期表。
5. **trace/run 贯穿异步链路**：同一部电影/同一集的生命周期可串联。

## Goals

1. 统一回答“识别 → 下载 → 转移 → 刮削 → 入库”当前在哪一步。
2. 保留失败、重试、排队、死信和时间线。
3. 支持电影单条、电视剧按季/集聚合。
4. 支持重新下载、重新刮削、多次运行，不混淆历史。
5. 可通过历史表回填，事件丢失时可对账修复。
6. 不改变现有下载/转移/刮削行为和状态语义。

## Non-Goals

- 不实现第二套工作流引擎。
- 不让生命周期状态成为订阅完成、下载准入或转移判断的依据。
- 不把 `TorrentStatus`、`SubscribeState` 等强行改成同一个枚举。
- 不在第一版覆盖播放、字幕、洗版、重命名全部状态。
- 不对每次进度轮询写事件；只记录阶段转换和关键失败/重试。

## Lifecycle Model

### Stage

```python
class LifecycleStage(str, Enum):
    IDENTIFIED = "identified"
    SUBSCRIBED = "subscribed"
    SEARCHING = "searching"
    DOWNLOAD_QUEUED = "download_queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSFER_QUEUED = "transfer_queued"
    TRANSFERRING = "transferring"
    TRANSFERRED = "transferred"
    SCRAPE_QUEUED = "scrape_queued"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    IN_LIBRARY = "in_library"
```

### Status

```python
class LifecycleStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    DEAD = "dead"
```

说明：

- `BLOCKED` 用于等待人工处理（例如缺少元数据、路径冲突）。
- `DEAD` 用于队列超过最大重试次数。
- 生命周期状态只描述当前阶段，不替代下载器的 `Paused/Seeding` 等细节。

### 电影与电视剧

```text
电影：IDENTITY_ID + SEASON=0 + EPISODE=0
电视剧/动漫：IDENTITY_ID + SEASON + EPISODE
整季/整剧状态：由单集状态聚合
```

聚合规则建议：

- 任意单集 `DEAD/FAILED` → 整剧 `FAILED`（`has_errors=true`）
- 存在未完成单集 → 整剧 `RUNNING` 或 `QUEUED`
- 全部单集 `IN_LIBRARY` → 整剧 `IN_LIBRARY`
- 未开播/未监控单集不参与完成度

## Data Model

### MEDIA_LIFECYCLE

当前状态快照，按身份 + 季 + 集唯一。

| 字段 | 类型 | 说明 |
|---|---|---|
| ID | bigint | 主键 |
| IDENTITY_ID | varchar(26) | 媒体身份（ADR-014/025） |
| MEDIA_TYPE | varchar(16) | movie/tv/anime |
| SEASON | int | 电影为 0 |
| EPISODE | int | 电影为 0 |
| STAGE | varchar(32) | `LifecycleStage` |
| STATUS | varchar(16) | `LifecycleStatus` |
| RUN_ID | varchar(64) | 本次获取运行 |
| TRACE_ID | varchar(64) | 贯穿异步链路 |
| PROGRESS | int | 0-100，仅展示 |
| SOURCE_PROVIDER | varchar(64) | 资源来源/元数据来源 |
| CONTENT_PROFILE | varchar(64) | 内容画像 |
| USER_ID | bigint nullable | 归属用户 |
| STAGE_STARTED_AT | datetime | 当前阶段开始 |
| LAST_EVENT_AT | datetime | 最近事件 |
| NEXT_RETRY_AT | datetime nullable | 下次重试 |
| RETRY_COUNT | int | 当前阶段重试次数 |
| LAST_ERROR | text nullable | 最近错误 |
| CREATED_AT / UPDATED_AT | datetime | 审计 |

唯一约束：

```text
UNIQUE(IDENTITY_ID, SEASON, EPISODE)
```

索引：

```text
(USER_ID, STATUS, LAST_EVENT_AT)
(STAGE, STATUS, LAST_EVENT_AT)
(TRACE_ID)
```

### MEDIA_LIFECYCLE_EVENT

只追加时间线。

| 字段 | 类型 | 说明 |
|---|---|---|
| ID | bigint | 主键 |
| EVENT_KEY | varchar(128) | 幂等键，唯一 |
| IDENTITY_ID | varchar(26) | 身份 |
| SEASON / EPISODE | int | 集维度 |
| RUN_ID | varchar(64) | 运行 |
| TRACE_ID | varchar(64) | 链路 |
| STAGE | varchar(32) | 阶段 |
| EVENT_TYPE | varchar(64) | 如 download.started |
| STATUS | varchar(16) | 统一状态 |
| MESSAGE | varchar(512) | 展示信息 |
| PAYLOAD | json/text | 队列、任务 ID、路径、错误摘要 |
| OCCURRED_AT | datetime | 事件发生时间 |
| CREATED_AT | datetime | 入库时间 |

唯一约束：

```text
UNIQUE(EVENT_KEY)
```

事件保留建议：

- 当前状态永久保留
- 事件默认保留 180 天，可配置
- 只记录阶段转换、失败、重试、完成，不记录每次进度轮询

## Trace and Run

### Run

一次“获取该媒体”的完整尝试：

```text
一次订阅/手动下载/补下载 = 一个 run
```

`RUN_ID` 在搜索或订阅创建下载意图时生成。重新下载、重新刮削时可创建新 `RUN_ID`，但生命周期事件仍可按 `IDENTITY_ID + SEASON + EPISODE` 聚合查看。

### Trace

`TRACE_ID` 用于跨队列和事件串联，必须进入：

- 搜索/下载意图
- download 队列 payload
- downloader 任务记录
- transfer/sync 队列 payload
- scrape 队列 payload
- 最终 `transfer_finished` / `media.scraped` 事件

规则：

```text
trace_id 不由 worker 重新生成
下游任务必须继承上游 trace_id
```

## Status Mapping

映射集中在一个模块，例如：

```text
src/app/domain/lifecycle.py
```

禁止在各 service 内散落映射。

### TaskStatus

```text
TaskStatus.QUEUED     -> QUEUED
TaskStatus.RUNNING    -> RUNNING
TaskStatus.SUCCEEDED  -> SUCCEEDED
TaskStatus.FAILED     -> FAILED
TaskStatus.CANCELLED  -> CANCELLED
TaskStatus.DEAD       -> DEAD
```

### Download

```text
DOWNLOAD_HISTORY.STATE:
  queued      -> DOWNLOAD_QUEUED / QUEUED
  downloading -> DOWNLOADING / RUNNING
  completed   -> DOWNLOADED / SUCCEEDED
  error       -> DOWNLOADING / FAILED

TorrentStatus:
  Pending/Queued -> DOWNLOAD_QUEUED / QUEUED
  Downloading    -> DOWNLOADING / RUNNING
  Checking       -> DOWNLOADING / RUNNING
  Paused/Stopped -> DOWNLOADING / BLOCKED
  Error          -> DOWNLOADING / FAILED
  Uploading      -> DOWNLOADED / SUCCEEDED
```

### Subscribe

```text
D -> SUBSCRIBED / QUEUED
S -> SEARCHING / RUNNING
R -> SUBSCRIBED / RUNNING
C -> DOWNLOADED / SUCCEEDED
E -> SUBSCRIBED / FAILED
N -> SUBSCRIBED / CANCELLED
```

### Transfer

```text
transfer queue queued/running/succeeded/dead
  -> TRANSFER_QUEUED/TRANSFERRING/TRANSFERRED/TRANSFER_QUEUED(dead)

TRANSFER_HISTORY:
  SOURCE_STATE/DEST_STATE present -> TRANSFERRED / SUCCEEDED
  missing/deleted                 -> TRANSFERRED / FAILED or BLOCKED
```

### Scrape

```text
scrape queue queued/running -> SCRAPE_QUEUED/SCRAPING
scrape success              -> SCRAPED / SUCCEEDED
scrape dead                 -> SCRAPING / DEAD
```

### Library

```text
LibraryPresenceService present -> IN_LIBRARY / SUCCEEDED
```

## Projector

### Inputs

1. 现有领域事件（EventBus）
2. 队列任务状态变化（入队/开始/失败/完成）
3. 下载/转移/同步/订阅历史表
4. `LibraryPresenceService` 对账结果

### Write rules

- 仅 `LifecycleProjector` 写两张生命周期表
- 事件幂等：`EVENT_KEY` 唯一，重复直接忽略
- 当前状态更新必须比较 `OCCURRED_AT` 或版本，避免旧事件覆盖新状态
- 一个事务内：写事件 + 更新当前快照
- 未知阶段/状态写 `unknown` 并告警，不静默丢弃

### 推荐事件类型

```text
lifecycle.identified
lifecycle.subscribed
lifecycle.search.started
lifecycle.download.queued
lifecycle.download.started
lifecycle.download.completed
lifecycle.download.failed
lifecycle.transfer.queued
lifecycle.transfer.started
lifecycle.transfer.completed
lifecycle.transfer.failed
lifecycle.scrape.queued
lifecycle.scrape.started
lifecycle.scrape.completed
lifecycle.scrape.failed
lifecycle.library.present
lifecycle.library.missing
```

### Reconciliation

事件不能作为唯一来源：

- 下载历史、转移历史、同步历史仍可能先写/后写
- 队列 ACK 后任务状态可能消失
- 进程重启可能丢事件

因此增加定时对账：

```text
每 5 分钟：
  1. 扫描最近 24h 的 DOWNLOAD_HISTORY / TRANSFER_HISTORY / SUBSCRIBE_HISTORY
  2. 对比生命周期当前状态
  3. 缺失事件补写
  4. 长期停在 RUNNING 且无心跳的任务标记 BLOCKED
  5. 记录 projection lag / unknown state 指标
```

## API Design

### 列表

```http
GET /api/media/lifecycle?stage=&status=&media_type=&user_id=&keyword=&page=&pagenum=
```

返回：

```json
{
  "items": [
    {
      "identity_id": "...",
      "title": "示例电影",
      "media_type": "movie",
      "season": 0,
      "episode": 0,
      "stage": "downloading",
      "status": "running",
      "progress": 42,
      "stage_started_at": "2026-11-02T10:00:00+08:00",
      "elapsed_seconds": 380,
      "retry_count": 0,
      "last_error": "",
      "source_provider": "tmdb",
      "trace_id": "..."
    }
  ],
  "total": 1
}
```

### 详情/时间线

```http
GET /api/media/lifecycle/{identity_id}?season=&episode=
GET /api/media/lifecycle/{identity_id}/events?season=&episode=&limit=200
```

时间线事件返回：

```json
{
  "stage": "scraping",
  "status": "running",
  "message": "正在生成 NFO 和海报",
  "occurred_at": "...",
  "elapsed_seconds": 12,
  "payload": {
    "queue": "scrape:file",
    "task_id": "...",
    "attempt": 1
  }
}
```

### 操作（第二阶段）

```http
POST /api/media/lifecycle/{identity_id}/retry
POST /api/media/lifecycle/{identity_id}/cancel
POST /api/media/lifecycle/{identity_id}/identify
```

这些接口必须委托原服务，不允许生命周期服务直接改业务状态。

### 权限

遵循 ADR-021：

- 普通用户：`USER_ID` 过滤
- 超级管理员：全部
- 共享站点/公共库按现有可见性
- payload 中禁止返回下载器凭据、Cookie、密钥

## Frontend Contract

页面建议：

```text
/media/lifecycle
```

组件：

```text
LifecyclePage
├── LifecycleStats
├── LifecycleFilters
├── LifecycleTable
└── LifecycleDrawer
    ├── LifecycleTimeline
    ├── EpisodeMatrix
    └── LifecycleActions
```

设计原型：

```text
frontend/design/media-lifecycle.html
```

前端状态颜色遵循 Tabler 变量：

```text
--tblr-primary  #206bc4
--tblr-success  #2fb344
--tblr-danger   #d63939
--tblr-warning  #f76707
--tblr-info     #4299e1
--tblr-teal     #0ca678
```

## Rollout

### Phase 0：基础

- 新增 `LifecycleStage` / `LifecycleStatus` / 映射模块
- 所有队列 payload、事件补 `run_id` / `trace_id`
- 映射单元测试

### Phase 1：投影与查询

- 新增两张表与迁移
- `LifecycleProjector`
- 列表、详情、时间线只读 API
- 历史回填脚本

### Phase 2：页面

- 生命周期列表
- 详情抽屉
- 电视剧集矩阵
- SSE 或轮询更新

### Phase 3：操作与对账

- 重试/取消/手动识别
- 定时对账
- 阶段耗时、失败率、卡住任务统计

## Acceptance Criteria

1. 重复事件不会产生重复生命周期事件。
2. 旧事件不会覆盖新阶段。
3. 同一电影两次下载可通过 `RUN_ID` 区分。
4. 电视剧可按季/集查看，整季状态由单集聚合。
5. 删除队列 stream 条目后，生命周期时间线仍可查询。
6. 投影丢失后可通过历史表回填恢复。
7. 普通用户无法看到其他用户的生命周期。
8. 生命周期页面操作不会直接修改业务表。

## Risks

| 风险 | 缓解 |
|---|---|
| 映射漂移 | 集中映射模块 + 测试 + unknown 告警 |
| trace 断链 | 队列 payload/event 强制继承，启动校验 |
| 投影滞后 | 5 分钟对账 + lag 指标 |
| 重复事件 | EVENT_KEY 唯一 + 事务更新 |
| 运行混淆 | RUN_ID + 事件保留 |
| 数据膨胀 | 事件 180 天保留，当前状态永久 |
| 权限泄露 | API 统一 owner scope + payload 脱敏 |

## References

- ADR-014：媒体身份解析与匹配架构
- ADR-021：多用户数据权限
- ADR-025：多源元数据订阅与刮削架构
- `src/app/infrastructure/task_queue/models.py`
- `src/app/services/scrape_queue_service.py`
- `src/app/services/transfer_queue_service.py`
- `frontend/design/media-lifecycle.html`
