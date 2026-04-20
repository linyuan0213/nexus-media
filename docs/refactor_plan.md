# NAS-Tools 项目重构计划文档

> 文档生成时间：2026-04-15  
> 范围：核心 Python 后端代码（`app/`、`web/`、`config.py`）

---

## 1. 概述

本文档基于对项目核心代码的逐模块审查，梳理出当前需要重构的模块清单。所有问题均围绕**代码可维护性、可测试性、职责单一性**展开，按优先级分为三层：

- **P0（高优先级）**：架构与核心服务层，存在 God Class、单例滥用、职责过重等结构性问题。
- **P1（中优先级）**：调度、数据访问与业务支撑层，存在新旧系统并存、巨型 Facade、重复代码等问题。
- **P2（低优先级）**：配置、搜索与生命周期管理，存在配置混杂、逻辑冗长、服务启停不统一等问题。

---

## 2. P0 高优先级：架构与核心服务层

### 2.1 Web 请求处理层 (`web/action.py` + `web/actions/_base.py`)

#### 2.1.1 现状问题

- **God Class**：通过 Mixin 组合形成了一个超大类 `WebAction`，运行时聚合了媒体、站点、下载、刷流、RSS、用户管理、系统设置等全部 Web 接口逻辑。
- **职责混乱**：`WebActionBase._actions` 字典中硬编码了 200+ 个命令映射，本质是把整个后端路由塞在一个类里。
- **代码重复**：`_commands` 字典被完整重复定义了两次（`_base.py` 行 247–258 与 260–271）。

#### 2.1.2 重构目标

1. 废弃 Mixin 组合模式，按业务域拆分为独立的 Controller/Service（如 `BrushController`、`DownloadController`、`MediaController`）。
2. `WebActionBase` 仅保留通用工具方法（`_success`、`_fail`）。
3. 使用基于函数或 Blueprint 的路由注册机制，替代巨型 `_actions` 字典。

#### 2.1.3 关键代码位置

- `web/action.py:17` — `WebAction`
- `web/actions/_base.py:42` — `_actions`
- `web/actions/_base.py:247` — 重复的 `_commands`

---

### 2.2 刷流任务模块 (`app/brushtask.py`) ✅ 已完成

#### 2.2.1 现状问题

- **God Class + 单例滥用**：`BrushTask` 混合了任务调度、RSS 解析、规则判断、下载控制、数据库操作、消息通知等 6 种以上职责。
- **构造时副作用**：`__init__` 直接调用 `init_config`，后者会停止服务、加载数据库、清理缓存并启动调度器，严重违反单一职责原则。
- **调度逻辑侵入业务**：手动维护 `_job_ids` 和 `_scheduler`，`stop_service` 与 `_start_task_jobs` 与 APScheduler 紧耦合。

#### 2.2.2 重构目标

1. 拆分为 `BrushTaskService`（纯业务）、`BrushTaskScheduler`（调度编排）、`BrushTaskRepository`（数据层）。
2. 移除 `SingletonMeta`，通过构造函数注入 `SchedulerService`、`Message`、`Downloader` 等依赖。
3. 将调度任务的增删改查委托给统一的 `SchedulerService`，不再在各业务类中手动维护 `_job_ids`。

**完成状态**：`app/brushtask.py` + `app/brushtask_rule.py` 已迁移至 `app/services/brush_core.py` + `app/services/brush_service.py`，旧文件已删除。

#### 2.2.3 关键代码位置

- `app/brushtask.py:23` — `BrushTask`
- `app/brushtask.py:40` — `__init__` / `init_config`
- `app/brushtask.py:73` — `_start_task_jobs`
- `app/brushtask.py:637` — `stop_service`

---

### 2.3 下载器模块 (`app/downloader/downloader.py`) ✅ 已完成

#### 2.3.1 现状问题

- **职责过多**：同时充当下载器客户端工厂、下载任务执行器、文件转移协调器、批量下载策略引擎、种子解析器。
- **方法过长**：`download` 超过 300 行，`batch_download` 超过 400 行，包含电影 / 整季 / 集匹配 / 部分下载等极度复杂的分支逻辑。
- **单例 + 构造时启动服务**：`__init__` 调用 `init_config`，后者直接调用 `start_service` 注册调度任务。

#### 2.3.2 重构目标

1. 拆分 `DownloadClientFactory`、`DownloadService`、`TransferCoordinator`、`BatchDownloadStrategy`。
2. 将 `batch_download` 中的策略逻辑提取为独立类：
   - `MovieDownloadStrategy`
   - `SeasonPackStrategy`
   - `EpisodeStrategy`
3. 下载器监控调度（`Downloader.transfer`）应与下载核心逻辑分离。

**完成状态**：已拆分为 `app/services/downloader_core.py`（Facade）、`app/services/download_core.py`、`app/services/transfer_coordinator.py`、`app/services/download_strategies.py`，旧文件已删除。

#### 2.3.3 关键代码位置

- `app/downloader/downloader.py:32` — `Downloader`
- `app/downloader/downloader.py:269` — `download`
- `app/downloader/downloader.py:802` — `batch_download`
- `app/downloader/downloader.py:225` — `start_service`

---

## 3. P1 中优先级：调度、数据访问与业务支撑层

### 3.1 调度器管理层 (`app/scheduler.py` + `app/scheduler_service.py`) ✅ 已完成

#### 3.1.1 现状问题

- **新旧两套系统并存**：旧代码 `SchedulerUtils.start_job` 直接操作底层 APScheduler；新代码 `SchedulerService` 虽已做较好封装，但整合不彻底。
- **重复代码**：`BrushTask`、`RssChecker`、`Downloader` 各自内部都有几乎相同的 `_scheduler.start_job` / `remove_job` / `_job_ids` 管理逻辑。

#### 3.1.2 重构目标

1. 强制统一使用 `SchedulerService` 作为唯一调度入口。
2. 各业务模块取消内部 `_scheduler` 和 `_job_ids` 字段，改为向 `SchedulerService` 注册命名空间任务，由服务统一启停。
3. 将 `app/scheduler.py` 中剩余的 `SchedulerUtils` 调用全部迁移到 `SchedulerService` API。

**完成状态**：`app/services/scheduler_core.py`（`SchedulerCore` 单例）与 `app/services/scheduler_service.py`（业务封装）已完成，各业务模块通过 `SchedulerCore` 统一注册任务。

#### 3.1.3 关键代码位置

- `app/scheduler.py:50` — `SchedulerUtils.start_job`
- `app/scheduler_service.py:169` — `SchedulerService`

---

### 3.2 数据库访问兼容层 (`app/helper/db_helper.py`)

#### 3.2.1 现状问题

- **巨型 Facade**：800+ 行的兼容层，所有方法均为对 `app/db/repositories/` 的简单透传代理。
- 虽然项目已引入 Repository 模式，但大量旧业务类仍通过 `DbHelper()` 访问数据库，形成新的瓶颈。

#### 3.2.2 重构目标

1. 明确 `DbHelper` 为**只删不增**的兼容层，禁止新增任何方法。
2. 推动业务模块（`BrushTask`、`Downloader`、`Filter`、`RssChecker` 等）直接注入所需的 `*Repository`，逐步淘汰 `DbHelper`。
3. 对新增的 Repository 统一补充单元测试（`tests/test_db_repositories.py` 已部分覆盖，需持续推进）。

#### 3.2.3 关键代码位置

- `app/helper/db_helper.py:51` — `DbHelper`

---

### 3.3 自定义 RSS 模块 (`app/rsschecker.py` / `app/rss.py`) ✅ 已完成

#### 3.3.1 现状问题

- 与 `BrushTask` 高度相似的单例 + 调度侵入 + 职责混杂问题。
- `init_config` 中混合了解析器加载、任务加载、调度启动。
- `check_task_rss` 方法过长，包含下载、订阅、搜索三种用途的复杂分支。
- XML/JSON 解析逻辑与业务主流程紧耦合。

#### 3.3.2 重构目标

1. 抽取 `RssTaskService`、`RssParserService`、`RssTaskScheduler`。
2. 将 XML/JSON 解析器抽象为统一接口（`RssParser`），支持插件式扩展。
3. 调度任务统一托管给 `SchedulerService`。

**完成状态**：`app/rss.py` 已重构为 `app/services/rss_service.py`（`RssTaskService` + `RssSubscriptionService` + `RssParserEngine`），旧文件已删除。

#### 3.3.3 关键代码位置

- `app/rsschecker.py:25` — `RssChecker`
- `app/rsschecker.py:50` — `init_config`
- `app/rsschecker.py:190` — `check_task_rss`

---

### 3.4 过滤规则模块 (`app/filter.py`)

#### 3.4.1 现状问题

- **数据加载与规则执行耦合**：`Filter` 类既负责从数据库加载规则组，又负责执行复杂的规则匹配。
- `check_rules` 和 `check_torrent_filter` 方法冗长，条件分支过多，难以单元测试。

#### 3.4.2 重构目标

1. 参考 `BrushRuleEngine`（`app/brushtask_rule.py`）的设计，将 `Filter` 拆分为：
   - `RuleRepository`（数据加载）
   - `FilterRuleEngine`（纯逻辑匹配）
2. 规则匹配逻辑改为基于策略链或规则对象列表的遍历，减少硬编码分支。

#### 3.4.3 关键代码位置

- `app/filter.py:13` — `Filter`
- `app/filter.py:96` — `check_rules`
- `app/filter.py:245` — `check_torrent_filter`

---

## 4. P2 低优先级：配置、搜索与生命周期管理

### 4.1 配置管理模块 (`config.py`) ✅ 已完成

#### 4.1.1 现状问题

- **单例实现不统一**：同时存在 `@singleconfig` 装饰器（全局变量 `_CONFIG`）和项目其他地方大量使用的 `SingletonMeta`。
- **职责混杂**：`Config` 类中混合了 YAML 配置读写、网络请求（`_check_sites_update`）、路径计算、图片代理 URL 处理等无关逻辑。

#### 4.1.2 重构目标

1. 统一配置中心接口，移除 `@singleconfig` 或统一改用 `SingletonMeta`。
2. 将 `sites.dat` 自动更新逻辑拆分到 `SiteDataUpdater`。
3. 将图片 URL 代理逻辑拆分到 `ImageProxyHelper`。

**完成状态**：
- `@singleconfig` 已移除，`Config` 改用 `SingletonMeta` 实现单例，`Config()` 调用方式完全不变
- `app/helper/site_data_updater.py`：`SiteDataUpdater` 封装 `sites.dat` 下载、版本比较、更新检查
- `app/helper/image_proxy_helper.py`：`ImageProxyHelper` 封装 TMDB/豆瓣/Bangumi 图片代理 URL 生成
- 调用方 `initializer.py`、`app/services/media_service.py`、`app/media/*.py` 等已迁移至直接调用新 Helper
- 新增 `tests/services/test_config_refactor.py`（23 个用例全部通过）

#### 4.1.3 关键代码位置

- `config.py:120` — `@singleconfig`
- `config.py:132` — `Config`
- `config.py:179` — `_check_sites_update`

---

### 4.2 搜索模块 (`app/searcher.py`) ✅ 已完成

#### 4.2.1 现状问题

- `search_one_media` 方法职责不单一，混合了搜索词构建、多语言扩展、线程池并发、结果去重、下载历史过滤、择优下载。
- 线程池管理设计不清晰：全局变量 `_search_executor` 与上下文管理器 `search_executor_context` 并存。

#### 4.2.2 重构目标

1. 拆分 `SearchQueryBuilder`（构建搜索词）、`SearchExecutor`（执行并发搜索）、`SearchResultDeduplicator` / `SearchResultProcessor`（去重与过滤）。
2. 统一线程池生命周期管理，避免全局变量与上下文管理器混用。

**完成状态**：`app/searcher.py` 已重构为 `app/services/search_service.py`（Searcher Facade 保留 SingletonMeta，内部使用 `SearchQueryBuilder`、`SearchExecutor`、`SearchResultDeduplicator`、`SearchResultProcessor`），旧文件已删除。

#### 4.2.3 关键代码位置

- `app/searcher.py:19` — `_search_executor`
- `app/searcher.py:31` — `search_executor_context`
- `app/searcher.py:94` — `search_one_media`

---

### 4.3 服务生命周期管理（跨模块） ✅ 已完成

#### 4.3.1 现状问题

- 各后台服务（`BrushTask`、`Downloader`、`RssChecker`、`Sync`、`TorrentRemover` 等）的 `stop_service` 实现不统一：有的只移除调度 job，有的不完整，有的直接 `print(str(e))` 而非使用日志框架。
- `WebActionBase.stop_service` 需要硬编码调用每一个单例的静态方法，新增服务时容易遗漏。

#### 4.3.2 重构目标

1. 引入统一的生命周期管理器（`ServiceRegistry` 或 `LifecycleManager`）。
2. 所有后台服务实现统一的 `start()` / `stop()` 接口并注册到管理器中。
3. 由管理器统一负责启动顺序和优雅停机，避免硬编码罗列。

**完成状态**：`SystemLifecycleService`（`app/services/system_service.py`）已实现统一编排，`start_service()` 按顺序启动 `SchedulerCore` → 各业务服务 → `init_config()`；`stop_service()` 统一优雅停机。各服务 `__init__` 中已移除自动 `init_config()`。

#### 4.3.3 关键代码位置

- `web/actions/_base.py:303` — `WebActionBase.stop_service`
- `web/actions/_base.py:326` — `WebActionBase.start_service`

---

## 5. 重构优先级矩阵

| 优先级 | 模块 | 核心痛点 | 预期收益 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | `web/actions/` | God Class、Mixin 组合失控 | 降低复杂度、便于分域维护 | ⏳ 待处理 |
| **P0** | `app/brushtask.py` | God Class、单例滥用、构造时副作用 | 提升可测试性、减少调度耦合 | ✅ 已完成 |
| **P0** | `app/downloader/downloader.py` | 方法过长、职责过多、策略混杂 | 代码清晰、便于新增下载器 | ✅ 已完成 |
| **P1** | `app/scheduler.py` + `scheduler_service.py` | 新旧调度 API 并存、重复代码 | 统一调度入口、降低维护成本 | ✅ 已完成 |
| **P1** | `app/helper/db_helper.py` | 巨型 Facade、阻碍 Repository 模式落地 | 数据层现代化、提升可测试性 | ⏳ 待处理 |
| **P1** | `app/rsschecker.py` | 与 BrushTask 类似的结构问题 | 统一任务模式、提升可扩展性 | ✅ 已完成 |
| **P1** | `app/filter.py` | 数据与逻辑耦合、分支冗长 | 规则引擎化、单测友好 | ⏳ 待处理 |
| **P2** | `config.py` | 单例不统一、职责混杂 | 配置中心清晰化 | ✅ 已完成 |
| **P2** | `app/searcher.py` | 搜索流程过长、线程池混乱 | 搜索逻辑模块化 | ✅ 已完成 |
| **P2** | 生命周期管理（跨模块） | 启停逻辑散落、不一致 | 统一优雅启停 | ✅ 已完成 |

---

## 6. 实施建议

1. **按 P0 → P1 → P2 顺序推进**，优先将 `WebAction`、`BrushTask`、`Downloader` 三大 God Class 拆分为职责单一的 **Service + Scheduler + Repository** 三层结构。
2. **每次重构一个业务域**，确保该域内的 Controller、Service、Repository、单元测试同时完成，避免半拉子工程。
3. **保留兼容层但限制其增长**：`DbHelper` 等兼容层在重构过渡期可以保留，但**严禁新增方法**。
4. **测试驱动**：对拆分出的 `BrushRuleEngine`、`SchedulerService`、`*Repository` 等模块优先补齐 `pytest` 用例（已有 `tests/` 目录，按项目规范在此创建）。
5. **文档同步**：每次重构完一个模块，同步更新本文档的状态列，记录已完成的拆分项和遗留项。

## 7. 已完成的额外重构

以下模块虽不在原始优先级矩阵中，但已随本轮重构同步完成：

| 原文件 | 新位置 | 说明 |
| :--- | :--- | :--- |
| `app/filetransfer.py` | `app/services/filetransfer_service.py` | 文件转移业务服务化 |
| `app/subscribe.py` | `app/services/subscribe_service.py` | 订阅管理服务化 |
| `app/sync.py` | `app/services/sync_core.py` + `app/services/sync_service.py` | 目录同步核心 + 业务服务分离 |
| `app/torrentremover.py` | `app/services/torrentremover_core.py` | 删种任务服务化（Repository + ActionEngine） |
| `app/system_service.py` | `app/services/system_service.py` | 顶层函数迁移至 `SystemLifecycleService` 等类 |

> 所有旧文件均已删除，调用方导入路径已统一更新为 `app.services.*`。

---

*文档结束*
