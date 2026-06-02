# ADR-007: 订阅与 RSS 流程概念澄清及架构重构方案

## Status

Accepted

## Date

2026-05-31

## Context

当前系统的"订阅自动下载"功能由两条完全独立的流水线实现，共用"RSS"和"订阅"两个词，导致用户无法区分，开发者维护困难。

### 当前三条并行的"RSS"流水线

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户视角："RSS 订阅"                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. RSS 订阅下载 (rss_core.py)          2. 订阅搜索 (subscribe_search_engine.py) │
│     ├─ 触发：pt_check_interval (秒)        ├─ 触发：search_rss_interval (小时)    │
│     ├─ 数据源：站点 RSS Feed               ├─ 数据源：主动搜索索引器              │
│     ├─ 范围：state="R" 的所有订阅          ├─ 范围：state="R" / "D" 的订阅       │
│     └─ 前端名称："电影/电视剧订阅"           └─ 前端名称："订阅搜索"              │
│                                                                             │
│  3. 自定义 RSS (RssTaskService)                                              │
│     ├─ 触发：用户自定义 interval/cron                                       │
│     ├─ 数据源：用户填写的任意 RSS URL                                        │
│     └─ 前端名称："自定义 RSS"                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 核心问题

#### 问题 1："RSS"一词严重过载

| 场景 | 实际含义 |
|------|---------|
| `rss_core.py` | 站点 RSS Feed 轮询，为订阅匹配新资源 |
| `RssTaskService` | 用户自定义 RSS 自动化任务（下载/订阅） |
| `RssMovie` / `RssTv` (DB表) | 订阅数据实体，与 RSS 协议无关 |
| `/api/rss/*` (路由) | 订阅 CRUD API |
| `rss_sites` (字段) | 订阅关联的站点范围 |

一个新人搜索 "RSS" 会同时命中三条完全不同的业务线。

#### 问题 2：用户无法区分"RSS订阅"和"订阅搜索"

前端服务面板显示：
- "电影/电视剧订阅" → 实际做的是 RSS Feed 轮询
- "订阅搜索" → 实际做的是主动搜索索引器

两者目标完全一致（自动下载订阅内容），用户不关心数据源是 RSS 还是索引器。当前的拆分让用户困惑："为什么有两个服务做同一件事？"

#### 问题 3：后端/前端/数据库命名不一致

```
前端菜单    : "RSS 订阅"
后端模块    : app/services/subscribe/
后端 API    : /api/rss/*
数据库表    : RSS_MOVIE, RSS_TV, RSS_HISTORY
领域实体    : RssMovieEntity, RssTvEntity
调度任务    : Rss.rssdownload / Subscribe.subscribe_search_all
```

#### 问题 4：重复下载路径，无中央协调

同一个订阅可以被以下任意流程满足：
1. `Rss.rssdownload()` — RSS Feed 轮询
2. `SubscribeSearchEngine.subscribe_search(state="D")` — 队列搜索（高频）
3. `SubscribeSearchEngine.subscribe_search_all()` — 主动搜索（低频）
4. `RssTaskService` — 自定义 RSS（如果 uses="R"）

各流程之间无协调，虽然分布式锁防止同一实例并发，但多实例仍可能竞争下载同一资源。

#### 问题 5：状态机对用户完全隐藏

订阅内部状态：
- **D** (Delayed/Pending)：新添加，需要立即搜索已有资源
- **S** (Searching)：正在执行搜索
- **R** (Running)：已被 RSS 轮询和主动搜索监控
- **C** (Completed)：已完成

用户在前端看不到这些状态，也无法理解为什么刚添加的订阅没有立刻开始搜索。

---

## 目标

1. **统一概念**：将"订阅自动下载"抽象为单一领域概念，无论数据源是 RSS 还是索引器
2. **消除"RSS"过载**："RSS"只保留给真正的 RSS 协议相关功能（自定义 RSS）
3. **后端命名对齐**：模块、API、数据库表统一使用"Subscribe/Subscription"
4. **统一自动下载入口**：所有订阅的自动下载由单一调度器触发，内部按策略选择数据源
5. **状态机可视化**：前端显示订阅状态，让用户理解当前处于哪个阶段
6. **可测试性**：拆分策略类，支持独立单元测试

---

## 方案设计

### 新领域概念

| 旧名称 | 新名称 | 说明 |
|--------|--------|------|
| RSS 订阅 | **媒体订阅** (Media Subscription) | 用户订阅某部电影/剧集，系统自动下载 |
| RSS 订阅下载 | **订阅监控** (Subscription Monitor) | 被动轮询 + 主动搜索的统一调度器 |
| 订阅搜索 | **(合并入订阅监控)** | 不再作为独立服务暴露 |
| 自定义 RSS | **RSS 自动化任务** (RSS Automation) | 保留，与订阅完全分离 |
| RSS Movie/TV | Subscribe Movie/TV | 数据库表和实体重命名 |

### 架构重构

#### 重构前

```
┌─────────────────┐     ┌──────────────────────┐
│  Rss.rssdownload │     │ SubscribeSearchEngine │
│  (RSS Feed 轮询) │     │  (主动索引器搜索)      │
└────────┬────────┘     └──────────┬───────────┘
         │                         │
         └──────────┬──────────────┘
                    ▼
           ┌─────────────────┐
           │  SubscribeService │
           │  (完成/更新状态)   │
           └─────────────────┘
```

#### 重构后

```
┌─────────────────────────────────────────────────────┐
│           SubscriptionMonitor (统一调度器)            │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ RssFeedStrategy│  │ SearchStrategy│  │ QueueStrategy│ │
│  │ (RSS Feed轮询) │  │ (主动搜索)     │  │ (队列搜索)    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         └─────────────────┼─────────────────┘        │
│                           ▼                          │
│              ┌─────────────────────────┐             │
│              │   DownloadCoordinator   │             │
│              │  (去重/防重/优先级排序)   │             │
│              └─────────────────────────┘             │
└─────────────────────────────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  SubscribeService │
                  │  (状态管理/完成)   │
                  └─────────────────┘
```

### 目录结构变更

```
重构前                          重构后
─────────────────────────────────────────────────────────
app/services/
├── rss_core.py                 ├── subscribe/
│   (class Rss)                 │   ├── monitor.py          ← 统一调度器
│                               │   ├── coordinator.py      ← 下载协调器
│                               │   ├── matcher.py          ← 订阅匹配器
│                               │   ├── search_engine.py    ← 手动搜索 facade
│                               │   ├── strategies/
│                               │   │   ├── base_search.py  ← 搜索策略基类
│                               │   │   ├── rss_feed.py     ← RSS 轮询策略
│                               │   │   ├── indexer_search.py ← 主动搜索策略
│                               │   │   └── queue_search.py   ← 队列搜索策略
│                               │   └── management/
│                               │       ├── add_service.py       ← 添加订阅
│                               │       ├── update_service.py    ← 更新订阅设置
│                               │       ├── finish_service.py    ← 完成订阅
│                               │       ├── query_service.py     ← 查询订阅列表/详情
│                               │       ├── history_service.py   ← 订阅历史 CRUD
│                               │       ├── calendar_service.py  ← 订阅日历事件
│                               │       ├── refresh_service.py   ← 刷新订阅搜索
│                               │       ├── service.py           ← 订阅管理 facade
│                               │       └── utils.py             ← 订阅工具方法
│
├── rss/                        ├── rss_automation/           ← 原 rss/ (自定义RSS)
│   ├── task_service.py         │   ├── task_service.py      ← 任务调度管理
│   ├── _executor.py            │   ├── executor.py          ← RSS 解析执行器
│   ├── _articles.py            │   └── articles.py          ← 文章过滤/处理
│   └── parser.py               │
│                               └── userrss_service.py       ← 原 userrss_service.py
│                                   (用户自定义RSS的API facade)
│
app/api/routers/
├── rss.py                      ├── subscription.py           ← 订阅 CRUD / 历史
│                               └── rss_automation.py        ← 自定义RSS任务
└── userrss.py                  └── (删除，合并到 rss_automation.py)
```

### 各模块职责

| 模块 | 职责 | 与订阅的关系 |
|------|------|-------------|
| `subscribe/monitor.py` | 统一调度器，按策略分时触发 | 核心入口 |
| `subscribe/coordinator.py` | 下载锁、去重、优先级排序 | 被 strategies 调用 |
| `subscribe/matcher.py` | 订阅匹配器（判断种子是否命中订阅） | 被 monitor 调用 |
| `subscribe/search_engine.py` | 手动搜索 facade（用户前端触发） | 独立服务，不直接参与自动下载 |
| `subscribe/strategies/` | RSS 轮询、主动搜索、队列搜索三种策略 | 被 monitor 调用 |
| `subscribe/management/` | 订阅的添加、完成、更新、查询、历史、日历 | 被 monitor 和 API 调用 |
| `rss_automation/` | 用户自定义 RSS URL 的自动化任务 | **完全独立**，与订阅无耦合 |

### 数据库表重命名（可选，长期）

| 旧表名 | 新表名 |
|--------|--------|
| `RSS_MOVIE` | `SUBSCRIBE_MOVIE` |
| `RSS_TV` | `SUBSCRIBE_TV` |
| `RSS_TV_EPISODE` | `SUBSCRIBE_TV_EPISODE` |
| `RSS_HISTORY` | `SUBSCRIBE_HISTORY` |

> **注意**：表重命名需配合 Alembic 迁移，属于长期改造。

### 前端变更

#### 菜单重命名

```
重构前                          重构后
─────────────────────────────────────────────────────────
RSS 订阅                         媒体订阅
├── 电影订阅                      ├── 电影订阅
├── 剧集订阅                      ├── 剧集订阅
├── 自定义 RSS    ─────────────▶  ├── 自定义 RSS (RSS自动化)
└── 订阅历史                      └── 订阅历史

服务面板
├── 电影/电视剧订阅  ──────────▶  ├── 订阅监控 (被动轮询)
└── 订阅搜索         ──────────▶  └── (合并，不再独立显示)
```

#### 订阅状态可视化

前端订阅列表增加状态列：

```
┌──────────┬────────┬────────┬────────┬─────────────────┐
│ 名称      │ 类型   │ 季/集  │ 状态   │ 操作             │
├──────────┼────────┼────────┼────────┼─────────────────┤
│ 石纪元    │ 剧集   │ S04    │ 🟡搜索中│ 编辑 删除          │
│ 某电影    │ 电影   │ -      │ 🟢监控中│ 编辑 删除 立即搜索 │
│ 某剧集    │ 剧集   │ S01    │ 🟢监控中│ 编辑 删除 立即搜索 │
│ 旧订阅    │ 剧集   │ S02    │ 🟡待处理│ 编辑 删除 立即搜索 │
│ 已完成    │ 电影   │ -      │ 🔵已完成│ 删除             │
└──────────┴────────┴────────┴────────┴─────────────────┘

状态说明：
🟡 待处理/搜索中 — 刚添加，正在搜索已有资源
🟢 监控中 — 已进入自动监控，等待新资源发布
🔵 已完成 — 所有集已下载
🔴 错误 — 识别失败或其他错误
```

### API 路由变更

```
重构前                          重构后
─────────────────────────────────────────────────────────
/api/rss/movie/list      ───▶   /api/subscription/movie/list
/api/rss/movie/add       ───▶   /api/subscription/movie/add
/api/rss/tv/list         ───▶   /api/subscription/tv/list
/api/rss/tv/add          ───▶   /api/subscription/tv/add
/api/rss/history         ───▶   /api/subscription/history

/api/userrss/list        ───▶   /api/rss-automation/list
/api/userrss/add         ───▶   /api/rss-automation/add
```



### 调度任务合并

重构前：
- `Rss.rssdownload` — `pt_check_interval` (秒)
- `Subscribe.subscribe_search_all` — `search_rss_interval` (小时)
- `Subscribe.subscribe_search` — `RSS_CHECK_INTERVAL` (秒，队列)

重构后：统一为 `SubscriptionMonitor.run()`，内部按策略分时触发：

```python
class SubscriptionMonitor:
    def run(self):
        # 1. 队列搜索（高频）— 处理 state="D" 的订阅
        self._run_strategy(QueueSearchStrategy())

        # 2. RSS 轮询（中频）— 处理 state="R" 的订阅
        if self._should_run_rss():
            self._run_strategy(RssFeedStrategy())

        # 3. 主动搜索（低频）— 处理 state="R" 的订阅
        if self._should_run_search():
            self._run_strategy(IndexerSearchStrategy())
```

调度配置统一为：
- `subscribe.queue_interval` — 队列搜索间隔（秒）
- `subscribe.rss_interval` — RSS 轮询间隔（秒）
- `subscribe.search_interval` — 主动搜索间隔（小时）

### 下载协调器（防重复下载）

```python
class DownloadCoordinator:
    """防止多条流水线重复下载同一订阅的资源"""

    def __init__(self, cache):
        self._downloading: set[str] = set()  # tmdbid + season 指纹

    def try_acquire(self, media_info) -> bool:
        """尝试获取下载锁，成功返回 True"""
        key = f"{media_info.tmdb_id}:{media_info.get_season_string()}"
        if key in self._downloading:
            return False
        self._downloading.add(key)
        return True

    def release(self, media_info):
        key = f"{media_info.tmdb_id}:{media_info.get_season_string()}"
        self._downloading.discard(key)
```

---

## 实施步骤

### Phase 1：策略拆分与测试（不改变外部行为）

1. **创建 `app/services/subscribe/strategies/` 包**
   - 从 `rss_core.py` 提取 `RssFeedStrategy`
   - 从 `subscribe_search_engine.py` 提取 `IndexerSearchStrategy` 和 `QueueSearchStrategy`
   - 从 `download_strategies.py` 提取拆包下载策略

2. **创建 `DownloadCoordinator`**
   - 基于 Redis/内存的下载锁
   - 单元测试覆盖竞争场景

3. **保持所有旧代码可用**
   - 旧类内部调用新策略类
   - 前端和 API 不变

### Phase 2：统一调度器

4. **创建 `SubscriptionMonitor`**
   - 聚合三种策略
   - 按配置时间分时触发
   - 通过 `DownloadCoordinator` 防重

5. **替换调度任务**
   - 删除 `Rss.rssdownload` 和 `Subscribe.subscribe_search_all` 两个独立任务
   - 新增 `SubscriptionMonitor.run()` 单一任务

6. **状态机优化**
   - 新增 `E` (Error) 状态，用于识别失败等异常情况

---

## 订阅状态机（重构后）

### 状态定义

| 状态码 | 名称 | 说明 |
|--------|------|------|
| **D** | Pending (待处理) | 刚添加，需要立即搜索已有资源 |
| **S** | Searching (搜索中) | 正在被 `QueueSearchStrategy` 执行首次搜索 |
| **R** | Monitoring (监控中) | 已确认有缺失集或需要继续等待新资源，由 `SubscriptionMonitor` 统一轮询 |
| **C** | Completed (已完成) | 所有资源已下载入库 |
| **E** | Error (错误) | 识别失败或其他不可恢复错误 |

### 状态转换图

```
                          ┌───────────────────────────────────────┐
                          │                                       │
                          │   ┌──────────┐   下载完成/已存在      │
                          │   │          │◄──────────────────────┤
                          │   │    C     │                        │
                          │   │ (已完成) │                        │
                          │   └────▲─────┘                        │
                          │        │                              │
                          │        │ 全部资源下载完成               │
                          │        │                              │
┌──────────┐  添加订阅   ┌┴───────┐│      ┌──────────┐            │
│          │────────────▶│        ││      │          │  监控发现   │
│   初始    │             │   D    ││      │    R     │◄───────────┤
│          │             │(待处理) ││      │(监控中)  │  新资源发布  │
└──────────┘             └────┬───┘│      └────┬─────┘            │
                              │    │           │                 │
                              │    │           │ 仍有缺失          │
                              │    │           │                 │
                              │    │      ┌────┴─────┐            │
                              │    │      │          │  下载失败    │
                              │    └─────▶│    S     │────────────┤
                              │   Monitor │(搜索中)  │             │
                              │   调度触发│          │             │
                              │           └────┬─────┘             │
                              │                │                   │
                              │                │ 识别失败           │
                              │                │                   │
                              │           ┌────┴─────┐             │
                              │           │          │             │
                              └──────────▶│    E     │             │
                               TMDB 无结果 │ (错误)   │             │
                                          └──────────┘             │
                                                                     │
                          └──────────────────────────────────────────┘
```

### 状态转换表

| 当前状态 | 触发条件 | 目标状态 | 执行逻辑 |
|----------|----------|----------|----------|
| **D** → | 用户添加订阅 | **S** | 写入数据库，state=D，由 `QueueSearchStrategy` 立即搜索 |
| **S** → | 搜索命中且全部下载完成 | **C** | `check_exists_medias()` 返回无缺失，`finish_rss_subscribe()` |
| **S** → | 搜索命中但仍有缺失 | **R** | `update_subscribe_tv_lack()`，state 设为 R，进入 `SubscriptionMonitor` 监控 |
| **S** → | 搜索未命中（无资源） | **R** | state 设为 R，等待 RSS 轮询或下次主动搜索 |
| **S** → | TMDB 识别失败 | **E** | 标记错误，前端显示"识别失败"，用户可手动修正 |
| **R** → | `RssFeedStrategy` 轮询命中且下载完成全部缺失 | **C** | `finish_rss_subscribe()` |
| **R** → | `IndexerSearchStrategy` 主动搜索命中且下载完成 | **C** | `finish_rss_subscribe()` |
| **R** → | 部分下载完成，仍有缺失 | **R** | `update_subscribe_tv_lack()`，继续保持监控 |
| **R** → | 用户手动触发"立即搜索" | **S** | 临时进入搜索状态，完成后根据结果转 R 或 C |
| **E** → | 用户手动修正并重新识别 | **S** | 重新执行队列搜索 |
| **C** → | 用户重新订阅（洗版） | **S** | 洗版模式下重新进入搜索流程 |

### 状态与策略的映射

| 状态 | 哪个策略处理 | 调度频率 |
|------|-------------|----------|
| D | `QueueSearchStrategy` | 高频（由 Monitor 每次 run 都检查） |
| S | `QueueSearchStrategy` | 同一时刻只能有一个 S 状态的订阅在搜索（按调度器单线程执行） |
| R | `RssFeedStrategy` + `IndexerSearchStrategy` | 中频/低频（按各自 interval 独立触发） |
| C | 无 | 不参与任何策略 |
| E | 无 | 不参与任何策略，等待用户干预 |

### 关键设计决策

1. **D → S 是自动的**：用户添加订阅后无需手动触发，Monitor 下一次 run 时会自动发现 D 状态并启动队列搜索。

2. **S 状态是瞬态的**：理想情况下 S 只持续一个搜索周期（几秒到几分钟）。如果搜索过程中系统重启，重启后 Monitor 会重新发现 D 状态并再次搜索。

3. **R 状态是稳态的**：大部分活跃订阅长期处于 R 状态，等待新资源发布。R 状态的订阅会同时被 `RssFeedStrategy`（RSS 轮询）和 `IndexerSearchStrategy`（主动搜索）处理。

4. **E 状态需要用户干预**：识别失败不会自动重试，避免无限循环消耗资源。用户在前端看到 E 状态后可以手动修改标题/年份后重新识别。

5. **"立即搜索"按钮只在 D/R 状态可用**：S 状态正在执行搜索，不允许重复触发；E 状态需先修正错误；C 状态已完成无需搜索。

6. **C → S（洗版）**：洗版不是状态转换，而是创建一个新的"子订阅"，与原订阅并行追踪。洗版完成后原订阅保持 C，新订阅进入 C。

### Phase 3：命名对齐

7. **后端模块重命名**
   - `rss_core.py` → `subscribe/monitor.py`
   - `Rss` class → `SubscriptionMonitor`
   - `subscribe/` 目录 → `subscribe/management/`
   - `SubscribeSearchEngine` 内部方法合并到 `subscribe/strategies/`
   - `SubscribeSearchEngine` 保留为 `subscribe/search_engine.py`（手动搜索 facade）
   - `rss_automation/subscription.py`（`RssSubscriptionService`）拆分：
     - 添加/更新/删除订阅 → `subscribe/management/add_service.py` / `update_service.py` / `query_service.py`
     - 历史 CRUD → `subscribe/management/history_service.py`
     - 日历事件 → `subscribe/management/calendar_service.py`
     - 触发监控/刷新 → `subscribe/monitor.py`（`download_rss()` / `refresh_rss()`）
     - 判断种子命中 → `subscribe/matcher.py`（独立模块）

8. **API 路由迁移**
   - 创建 `/api/subscription/*` 新路由
   - 直接替换旧路由，不保留兼容

9. **前端菜单和文案更新**
   - "RSS 订阅" → "媒体订阅"
   - 服务面板合并 "订阅搜索" 到 "订阅监控"
   - 增加状态列和状态说明

### Phase 4：数据库迁移（长期）

10. **Alembic 迁移**
    - 重命名表（可选，视复杂度决定）
    - 或仅添加视图别名

---

## 决策

等待 review 后按 Phase 逐步实施。

---

## Consequences

### 正面影响

- **用户理解成本降低**："媒体订阅"一个概念覆盖所有自动下载场景
- **开发者维护成本降低**：不再被"RSS"一词误导到三条不同业务线
- **可测试性提升**：策略类独立，可单独测试 RSS 轮询、主动搜索、队列搜索
- **防重复下载**：`DownloadCoordinator` 消除多流水线竞争
- **状态透明**：用户能看到订阅当前处于"搜索中"还是"监控中"

### 负面影响

- **API 迁移成本**：前端需要同步更新 API 路径
- **调度配置变更**：用户已有的 `pt_check_interval` / `search_rss_interval` 需要迁移到新配置
- **数据库表重命名风险**：若执行，需确保所有查询点同步更新
