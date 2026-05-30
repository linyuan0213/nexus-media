# ADR-005: 站点-订阅-搜索-下载-入库流程技术债务评估

## Status
Accepted

## Date
2026-05-30

## Context

对"站点设置 → 订阅 → 搜索 → 下载 → 入库"完整流程进行代码审查，评估各环节实现完整性、领域层使用情况以及潜在风险。

## 流程架构

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ SiteService  │───▶│ Subscribe    │───▶│ Searcher     │───▶│ Downloader   │───▶│ FileTransfer │
│              │    │ Service      │    │              │    │ Core         │    │ Service      │
│ 站点配置管理  │    │ 订阅CRUD/状态 │    │ 多站点并发搜索 │    │ 下载编排      │    │ 文件转移/入库 │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

## 一、流程完整性评估

| 环节 | 状态 | 说明 |
|------|------|------|
| 站点配置 → 订阅 | ✅ 完整 | `rss_sites`/`search_sites` 字段存储站点名 |
| 订阅 → 搜索 | ⚠️ 有缺陷 | `lack` 计算错误、洗版逻辑不支持 TV |
| 搜索 → 下载 | ⚠️ 有缺陷 | ~~并发搜索覆盖~~（已加锁）、批量下载遇错终止 |
| 下载 → 入库 | ⚠️ 有缺陷 | ~~全局锁阻塞~~（已改细粒度）、路径安全检查缺失 |
| 入库 → 历史 | ✅ 完整 | 历史记录写入正常 |

**缺失的关键反馈回路**：文件转移成功后，订阅的 `current_ep`/`lack` 不会自动更新，依赖下次搜索时重新检查媒体库。

## 二、P0 问题（严重影响稳定性/安全）

### 2.1 全局单锁阻塞所有下载器转移

- **位置**：`app/services/downloader_core.py:24`（模块级 `lock = Lock()`）
- **影响**：`transfer()` 方法对所有下载器加同一把锁，多下载器场景下完全串行，形成严重性能瓶颈
- **修复方向**：改为按下载器 ID 的细粒度锁（`dict[str, Lock]`）

### 2.2 `delete_history()` 可任意删除目录

- **位置**：`app/services/transfer/cleanup_service.py:130-174`
- **影响**：通过历史记录反向构造路径后调用 `shutil.rmtree()`，无路径安全检查。若历史记录被篡改或 TMDB 信息变化，可能删除错误目录
- **修复方向**：删除前校验目标路径是否在配置的媒体库路径范围内

### 2.3 文件覆盖条件优先级风险

- **位置**：`app/services/transfer/filetransfer_service.py:618`
- **代码**：`media.size > orgin_size and self._filesize_cover or udf_flag`
- **影响**：`and` 优先级高于 `or`，逻辑正确但可读性差；`orgin_size` 拼写错误
- **修复方向**：加括号明确优先级，修正拼写为 `original_size`

## 三、P1 问题（功能缺陷）

### 3.1 洗版逻辑只操作 movie_repo

- **位置**：`app/services/subscribe/service.py:158,170`
- **影响**：`update_subscribe_over_edition()` / `check_subscribe_over_edition()` 仅更新/检查电影仓库，TV 洗版时状态异常
- **修复方向**：增加 TV 类型仓库的洗版操作分支

### 3.2 批量下载首个失败即终止

- **位置**：`app/services/download_service.py:91-99`
- **影响**：`download_from_search_results()` 循环中遇到首个失败立即返回，剩余搜索结果全部丢弃
- **修复方向**：收集所有结果后返回批量状态（成功列表 + 失败列表）

### 3.3 ~~搜索表全局清空~~（已修复）

- **位置**：`app/services/search_service.py:216-219`
- **影响**：`persist_results()` 先 `delete_all_search_torrents()` 再插入，并发搜索互相覆盖
- **修复**：已加分布式锁 `search:persist_results`（ttl=60s），同时 `insert_search_results()` 内部使用 UPSERT 语义删除冲突记录

### 3.4 双重锁死锁风险

- **位置**：`app/services/subscribe_search_engine.py:84-102`
- **影响**：先获取分布式锁，再获取线程锁；若线程锁阻塞，分布式锁在超时前无法释放
- **修复方向**：调整锁获取顺序（先线程锁后分布式锁），或移除线程锁（分布式锁已足够）

### 3.5 `lack` 计算逻辑有误

- **位置**：`app/services/subscribe/add_service.py:162-165`
- **代码**：`lack = total - current_ep - 1`
- **影响**：当 `current_ep=0` 时 `lack=total-1`（应为 total）；`current_ep=total-1` 时 `lack=0`（正确）
- **修复方向**：修正为 `lack = max(0, total - current_ep)`

### 3.6 媒体信息识别失败后错误标记状态

- **位置**：`app/services/subscribe_search_engine.py:134-136`
- **影响**：TMDB 识别失败后状态设为 "R"（搜索中），下次搜索再次失败
- **修复方向**：识别失败应保留 "D"（待处理）或设为错误状态，避免无效循环

## 四、P2 问题（设计债务）

| 问题 | 位置 | 说明 |
|------|------|------|
| ~~领域实体未被使用~~ | `site_service.py` | ~~`SiteService` 直接调用 legacy `Sites` 类~~ → 已迁移 `SiteEntity` + `ISiteRepository` |
| 无事务边界 | `subscribe/add_service.py` | TV 订阅需同时写入 tv_repo + tv_episode_repo，无事务保护 |
| ~~路径前缀误判~~ | `transfer_pipeline.py:144-165` | ~~`/movies` 会错误匹配 `/movies2/something`~~ → 已修复（`os.path.normpath` + `os.sep`） |
| ~~函数内导入~~ | `history_manager.py:35-39` | ~~`__import__("os")`~~ → 已改为模块顶部导入 |
| 返回类型不一致 | `search_service.py:276-382` | `search_one_media()` 4 个返回位置返回的元组结构不同 |
| ~~状态更新逐条进行~~ | `download_service.py:357-374` | ~~`active_ids`/`completed_ids` 用 for 循环逐条调用~~ → 已改为 `batch_update_state()` |
| 变量拼写错误 | `download_core.py:286-317` | `sucess_epidised` 多处拼写错误（应为 `success_episodes`） |
| 客户端类型硬编码 | `download_core.py:256-272` | 硬编码判断 `"transmission"` / `"qbittorrent"` |

## 五、领域实体使用评估

| 实体 | 定义位置 | 是否被服务层使用 | 评价 |
|------|---------|-----------------|------|
| `SiteEntity` | `domain/entities/site.py` | ✅ 是（`SiteService` CRUD） | 已迁移 `ISiteRepository` + `SiteRepositoryAdapter` |
| `RssMovieEntity` | `domain/entities/rss.py` | ✅ 是（Adapter 内部） | 良好，有状态枚举 |
| `RssTvEntity` | `domain/entities/rss.py` | ✅ 是（Adapter 内部） | 良好，有进度属性 |
| `DownloadHistoryEntity` | `domain/entities/download.py` | ❌ 否 | 定义完善但服务层未使用 |
| `DownloadSettingEntity` | `domain/entities/download.py` | ❌ 否 | 定义完善但服务层未使用 |
| `TransferHistoryEntity` | `domain/entities/transfer.py` | ❌ 否 | 定义完善但服务层未使用 |
| `TransferTask` | `domain/entities/transfer_task.py` | ✅ 是 | 良好，统一同步和下载器转移 |

**总体评价**：领域实体层设计较为完善（特别是 RSS 相关实体），但服务层存在"新旧混合"现象——`SubscribeService` 已通过 Adapter 模式使用领域实体，但 `SiteService`、`DownloadService`、`FileTransferService` 仍大量依赖 legacy ORM 对象和字典。

## 六、修复建议优先级

### 立即修复（P0）

1. `downloader_core.py`：将模块级全局锁改为按下载器 ID 的细粒度锁
2. `cleanup_service.py`：`delete_history()` 中 `shutil.rmtree()` 前增加路径安全检查
3. `filetransfer_service.py`：加括号明确优先级，修正 `orgin_size` 拼写

### 近期修复（P1）

1. `subscribe/service.py`：洗版逻辑增加 TV 类型仓库操作
2. `download_service.py`：批量下载改为收集所有结果后返回
3. `search_service.py`：`persist_results()` 改为按会话隔离
4. `subscribe_search_engine.py`：修正双重锁获取顺序
5. `subscribe/add_service.py`：修正 `lack` 计算逻辑

### 中期优化（P2）（已完成）

1. ~~`site_service.py`：逐步迁移使用 `SiteEntity` 和 `ISiteRepository`~~ ✅ 已迁移 CRUD 操作（`get_site`/`delete_site`/`update_site`/`update_site_cookie_ua`）
2. ~~`transfer_pipeline.py`：修复路径边界判断~~ ✅ 已修复（`os.path.normpath` + `os.sep`）
3. ~~`history_manager.py`：移除函数内导入~~ ✅ 已改为模块顶部导入
4. ~~补充批量操作接口~~ ✅ `IDownloadHistoryRepository` 新增 `batch_update_state()`，`DownloadRepository` 按 state 分组批量更新
5. ~~`path_resolver.py`：后端实例缓存~~ ✅ 新增 `_backend_cache: dict[str, Any]`，`resolve_backend_by_id()` 优先读缓存

### 长期架构

1. 引入 Saga/事务协调器，保证长流程原子性
2. ~~增加事件驱动：转移成功后发送事件，订阅服务消费并更新进度~~ ✅ 已实现 `EpisodeTransferred` 事件
3. 统一所有 Service 层的 DTO 使用，消除 `Any` 返回类型

## Consequences

- 修复 P0 问题后可消除严重的稳定性和安全隐患
- 修复 P1 问题后 TV 订阅、批量下载、并发搜索等核心功能将更可靠
- 领域实体逐步下沉到服务层，提升代码可测试性和可维护性
- 为后续引入事务协调器和事件驱动架构打下基础
