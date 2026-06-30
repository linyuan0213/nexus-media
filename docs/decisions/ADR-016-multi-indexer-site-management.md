# ADR-016: 多索引器统一站点管理与并行搜索

## Status

Accepted

## Date

2026-06-29

## Context

### 当前架构全景

```
配置层:
  SystemConfig (SYSTEM_DICT 键值存储)
    ├── SearchIndexer   = "builtin"             (单值, 只能选一个)
    ├── IndexerConfig   = {jackett:{host,...}}   (第三方配置)
    └── UserIndexerSites = [1, 2, ...]           (builtin 选中站点的 CONFIG_SITE.ID 列表)

索引器层:
  Indexer._ensure_client()  →  加载 SearchIndexer 指定的一个客户端

  ┌─── BuiltinIndexer ───────────────────────────────────────┐
  │                                                          │
  │  get_indexers():                                        │
  │    SiteEngine (config/sites/*.json) → SiteDefinition     │
  │    SiteCache  (CONFIG_SITE 表) → 合并 cookie/note        │
  │    IndexerHelper → IndexerConf (站点完整配置)             │
  │                                                          │
  │  search() → 爬虫搜索 → _base 注入 _indexer_name          │
  │             builtin:  _indexer_name = "M-Team"           │
  │             jackett:  _indexer_name = "kickass"          │
  │             prowlarr: _indexer_name = "1337x"            │
  └──────────────────────────────────────────────────────────┘

搜索管线:
  SearchPipeline.process() → ResultFilter
    提取 _indexer_name → media_info.site
    输出 media_info 数组 (每个带 site 字段)

下载管线:
  pipeline._stage_resolve()
    优先级:
    ① 显式 download_setting 参数
    ② media_info.site → SiteCache.get_site_download_setting(name)
                        → 查 CONFIG_SITE.NOTE.download_setting
    ③ ClientFactory.default_download_setting_id
```

### 关键组件

#### SiteEngine → IndexerConf 转换链

`SiteEngine`（`src/app/sites/engine.py:175`）加载 `config/sites/{api,html}/*.json`，生成 `SiteDefinition` 对象。
`BuiltinIndexer.get_indexers()`（`src/app/indexer/client/builtin.py:86`）将 `SiteDefinition` 转为 flat dict，传给 `IndexerHelper.set_indexers()`。
然后遍历 `SiteCache.get_sites()`（`site_cache.py:159`），调用 `IndexerHelper.get_indexer()`（`configuration.py:32`）合并用户 DB 配置（cookie、ua、headers、api_key、bearer_token、pri、proxy），生成 `IndexerConf` 对象。

#### 第三方索引器 API

| 索引器 | 站点列表 API | 返回的字段 |
|--------|-------------|-----------|
| Jackett | `GET /api/v2.0/indexers?configured=true` | `[{id, name, type}]` |
| Prowlarr | `GET /api/v1/indexerstats?apikey=` | `{indexers: [{indexerId, indexerName}]}` |

#### 搜索结果注入

`_IIndexClient.search()`（`src/app/indexer/client/_base.py:105-111`）是基类方法，builtin 和第三方都走这里：

```python
for item in result_array:
    item["_indexer_name"] = indexer.name       # line 107
```

对 builtin 来说 `indexer.name` = "M-Team"（从 JSON 来）。
对 Jackett/Prowlarr 来说 `indexer.name` = 索引器返回的 `name` 字段（如 "kickass", "1337x"）。

**注意**：第三方索引器返回的站点名（来自 Jackett/Prowlarr API）可能与内置站点的命名不一致（如 `MTeam` vs `M-Team`）。搜索结果注入时 `_indexer_name` 用的是索引器 API 返回的原始名。

#### 下载设置解析优先级

`pipeline._stage_resolve()`（`src/app/downloader/pipeline.py:270-279`）：

```
1. 显式 download_setting 参数 → 直接使用
2. media_info.site → SiteCache.get_site_download_setting(name) → 查站点 NOTE 中的 download_setting
3. "-2" → download_attr = {}（不绑定任何下载设置）
4. 以上都无 → ClientFactory.default_download_setting_id
```

`SiteCache.get_site_download_setting()`（`site_cache.py:232-238`）遍历 `_site_by_ids`，匹配 `site["name"]`（来自 `SiteEntity.name`），返回 `site["download_setting"]`（来自 `CONFIG_SITE.NOTE.download_setting`）。

#### 订阅搜索站点过滤

订阅的 `search_sites` 是站点名列表，存储在 `RSS_MOVIES`/`RSS_TVS` 表中。在搜索时经由 `BaseSearchStrategy` → `Searcher.search_one_media()` → `filter_args["site"]` → `BuiltinIndexer.search()` 过滤——只搜索列表中指定的站点。

### 问题

| 问题 | 根因 | 严重度 |
|------|------|--------|
| **单索引器限制** | `SearchIndexer` 单值配置，`_ensure_client()` 只加载一个 | 高 |
| **第三方站点无站点级下载设置** | `_indexer_name` 目前虽然注入了但 `SiteCache.get_site_download_setting()` 只查 `CONFIG_SITE` 表，第三方无行 | 高 |
| **站点列表不含第三方** | `POST /api/sites` → `SiteService.get_sites()` → `SiteCache.get_sites()` 只返回 `CONFIG_SITE` 中的行 | 中 |
| **搜索可能重复** | 同一 PT 站同时存在于 builtin 和 Jackett，虽各自搜索结果不同但可能重复 | 中 |
| **第三方站点不可单独开关** | 没有 `UserIndexerSites` 等价物。`get_user_indexers(check=True)` 只过滤 builtin | 中 |

## 目标

1. **多索引器并行搜索**：builtin + Jackett + Prowlarr 同时搜索，结果聚合去重
2. **统一站点下载设置**：所有站点（不论来源）支持站点级 `download_setting` 绑定
3. **站点列表合并**：`POST /api/sites` 返回 builtin + 第三方站点，前端统一管理
4. **统一站点开关**：`INDEXER_SITE_CONFIG.enabled` 替代 `UserIndexerSites`
5. **同名去重**：同一 PT 站出现在多个索引器时，优先使用 builtin 的完整配置

### 职责边界

第三方索引器**只参与搜索**，不参与 PT 站点管理功能：

| 功能 | builtin | 第三方 |
|------|---------|--------|
| 搜索（手动/订阅/刷流） | ✅ | ✅ |
| 按站点绑定下载设置 | ✅ | ✅ |
| 站点开关（启用/禁用） | ✅ | ✅ |
| 站点数据刷新（做种/上传/下载/魔力） | ✅ | ❌ |
| RSS 订阅监控 | ✅ | ❌ |
| 自动签到 | ✅ | ❌ |
| 站点连通性测试 | ✅ | ❌ |
| 做种信息查询 | ✅ | ❌ |
| 站点日统计 | ✅ | ❌ |

`INDEXER_SITE_CONFIG` 只存**搜索相关**配置（`enabled`、`download_setting`），不含 PT 统计数据。站点列表合并时第三方站点只出现在搜索站点选择器中，不出现在 RSS/刷流/统计过滤结果中。

## 决策

### 架构

新增 `INDEXER_SITE_CONFIG` 表作为**所有站点的用户侧配置**。`Indexer` 改为持有多个客户端。

```
INDEXER_SITE_CONFIG (统一数据源)
  site_name (UNIQUE) | source | public | download_setting | enabled
─────────────────────┼────────┼────────┼──────────────────┼────────
  M-Team             │ builtin│ 0      │ 1                │ 1
  TNode              │ builtin│ 0      │ NULL             │ 0
  HDArea             │ jackett│ 0      │ 2                │ 1

         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
  BuiltinIndexer     Jackett        Prowlarr
  (JSON + DB)        (API)          (API)

         └───────────────┼───────────────┘
                         ▼
              Indexer (多客户端)
              ThreadPoolExecutor 并发搜索
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       site A,B       site B,D       site C,E
          │              │              │
          └──────────────┼──────────────┘
                         ▼
              (title, size) 去重
                         ▼
                  SearchPipeline

### 1. `INDEXER_SITE_CONFIG` 表

**不复用 `CONFIG_SITE` 的理由**：

- `CONFIG_SITE` 与 `config/sites/*.json` 强绑定。`SiteEngine._load()` 遍历 JSON 目录，`SiteCache._build_site_info()` 依赖 JSON 解析 `api_key_header`/`strict_url`。插入无关行会破坏 `SitesManager` 初始化流程。
- `CONFIG_SITE` 有 `COOKIE`、`API_KEY`、`RSSURL`、`SIGNURL` 等必填字段（虽然有些 nullable），第三方站点都不需要。
- `SITE_STATISTICS_HISTORY`、`SITE_USER_INFO_STATS` 等关联表也不适用。

```sql
CREATE TABLE INDEXER_SITE_CONFIG (
    id                 INTEGER PRIMARY KEY,
    site_name          VARCHAR(255) NOT NULL,
    source             VARCHAR(50)  NOT NULL DEFAULT 'builtin',
    public             TINYINT      DEFAULT 0,
    download_setting   INTEGER      DEFAULT NULL,
    enabled            TINYINT      DEFAULT 1,
    created_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(site_name)
);
```

> 注：`id` 列由 SQLAlchemy 根据 dialect 自动处理自增（SQLite 用 `AUTOINCREMENT`，MySQL/PostgreSQL 用 `SERIAL`/`IDENTITY`），避免在 DDL 中写死方言关键字。本表不通过 Alembic 迁移创建，由项目启动时的 `Base.metadata.create_all()` 自动建表。

### 1.1 Repository 与 Adapter 层

遵循项目现有分层：ORM 模型 + Repository（原始 SQLAlchemy 操作）+ Adapter（适配领域接口）。新增：

- **领域接口**：`src/app/domain/interfaces/indexer_site_config_repo.py`
  - `IIndexerSiteConfigRepository`
  - 方法：`upsert_site`, `get_by_name`, `list_all`, `list_enabled_names`, `update_enabled`, `update_download_setting`, `get_download_setting`, `migrate_from_user_indexer_sites`

- **ORM Repository**：`src/app/db/repositories/indexer_site_config_repository.py`
  - `IndexerSiteConfigRepository`
  - 直接操作 `INDEXER_SITE_CONFIG` 表，封装 dialect 无关 upsert。

- **Adapter**：`src/app/db/repositories/indexer_site_config_repo_adapter.py`
  - `IndexerSiteConfigRepositoryAdapter(IIndexerSiteConfigRepository)`
  - 持有 `IndexerSiteConfigRepository`，对外返回领域对象 / 简单 DTO，兼容旧调用风格。

业务层（`Indexer`、`SiteService`、`DownloadPipeline`、`IndexerService`）依赖 `IIndexerSiteConfigRepository`，由 DI 注入 Adapter 实例。

### 2. 写入策略

| 来源 | 触发时机 | 写入方式 |
|------|---------|---------|
| builtin | 启动时一次性迁移 | 读取 `UserIndexerSites`（CONFIG_SITE.ID 列表）→ 映射为站点名 → `IndexerSiteConfigRepositoryAdapter.upsert(..., source='builtin', enabled=1/0)` |
| builtin | `SiteCache.refresh()` 时 | 遍历已加载的站点名列表 → `upsert(..., source='builtin')`；若行已存在则保留其 `enabled`/`download_setting`，否则 `enabled=1` |
| jackett | `IndexerConfigService.save_config()` 成功保存后 | 调 `GET /api/v2.0/indexers?configured=true` → 遍历结果 → `upsert`，`public` 取自 API 返回的 `type == "public"` |
| prowlarr | 同上 | 调 `GET /api/v1/indexerstats?apikey=` → 遍历 `indexers` → 同上 |

**去重规则**：`site_name UNIQUE`。`upsert` 时 **不覆盖** `source` 字段：

```python
# 伪代码，Repository 层用 SQLAlchemy dialect 无关的 upsert 实现
stmt = insert(INDEXER_SITE_CONFIG).values(...)
stmt = stmt.on_conflict_do_update(
    index_elements=["site_name"],
    set_={
        "public": stmt.excluded.public,
        "enabled": stmt.excluded.enabled,
        "download_setting": stmt.excluded.download_setting,
        "updated_at": stmt.excluded.updated_at,
    },
).on_conflict_do_nothing(index_elements=["site_name"])  # 首次写入保留 source
```

效果：builtin 先写入的行不会被第三方覆盖；第三方重复写入时只更新 `enabled`、`public`、`download_setting`（如提供）。

**首次写入**：第三方站点 `enabled=1`（全部开启）。后续用户可在站点列表页逐个开关，走 `enabled` 列。

**实现提示**：不同 dialect 的 upsert 语法不同，Repository 应封装为 `upsert_site(site_name, source, public, enabled, download_setting)`，内部根据连接 dialect 选择 SQLAlchemy `on_conflict_do_update`（PostgreSQL/SQLite 3.24+）或先 `SELECT` 后 `INSERT/UPDATE`（兼容性回退）。禁止在业务层写 `INSERT OR IGNORE` / `ON DUPLICATE KEY UPDATE` 等方言 SQL。

### 2.1 站点开关（替代 `UserIndexerSites`）

内置索引器目前用 `SystemConfigKey.UserIndexerSites`（JSON 列表）过滤。第三方索引器没有对应机制。

`INDEXER_SITE_CONFIG.enabled` 统一替代：

```
旧方案（仅 builtin）:
  SystemConfigKey.UserIndexerSites = [1, 2, ...]   # CONFIG_SITE.ID 列表
  BuiltinIndexer.get_indexers(check=True) 按 ID 过滤

新方案（统一）:
  INDEXER_SITE_CONFIG
  site_name  source    enabled  public  download_setting
  ─────────  ────────  ───────  ──────  ────────────────
  M-Team     builtin   1        0       1
  TNode      builtin   0        0       NULL
  HDArea     jackett   1        0       2
  TL         jackett   0        0       NULL

  搜索:  WHERE enabled = 1
  订阅:  WHERE enabled = 1
```

迁移：启动时根据 `UserIndexerSites` 中的 CONFIG_SITE.ID 列表，找到对应站点名，写入 `INDEXER_SITE_CONFIG.enabled=1`；未在列表中的 builtin 站点写入 `enabled=0`。迁移逻辑由 `initializer.py` 在应用启动时调用 `IndexerSiteConfigRepository.migrate_from_user_indexer_sites()` 执行一次，并记录是否已迁移，避免重复执行。并行运行稳定后废弃旧字段。

### 2.2 依赖注入

新增 `IIndexerSiteConfigRepository` / `IndexerSiteConfigRepositoryAdapter` 需在 DI 中显式注册，并注入到以下服务：

| 消费方 | 用途 |
|--------|------|
| `Indexer` | `_filter_indexers()` 中过滤第三方已启用站点 |
| `SiteService` | `get_sites()` 合并第三方站点（简单/完整模式） |
| `DownloadPipeline` | `_stage_resolve()` 中按 `media_info.site` 回退查询 `download_setting` |
| `IndexerService` | `get_all_user_indexers()` / `get_third_party_sites()` |
| `SiteCache` | `refresh()` 时同步 builtin 行 |

注册方式沿用现有 `src/app/di/registry.py` + `src/app/di/factories.py` 显式工厂模式。`IndexerSiteConfigRepositoryAdapter` 依赖 `IndexerSiteConfigRepository` 或直接依赖 `BaseRepository` 的 session 工厂。

### 3. 多客户端搜索

`Indexer` 改为持有**所有已配置**的客户端，但搜索时**不要嵌套 ThreadPoolExecutor**（当前 `search_by_keyword` 内部已为 builtin 站点启动一个 `ThreadPoolExecutor`，若再在外层套一个按客户端的 executor，两层 workers 互相等待会导致潜在死锁和线程爆炸）。

正确做法：把“客户端 × 站点”扁平化为一个工作项列表，用**单层** `ThreadPoolExecutor` 并发执行。

```python
class Indexer:
    def __init__(
        self,
        search_pipeline: SearchPipeline,
        indexer_helper: IndexerHelper,
        site_cache: SiteCache,
        site_engine: SiteEngine,
        site_config_repo: IndexerSiteConfigRepositoryAdapter | None = None,
        progress_helper: ProgressTracker | None = None,
        download_repo: DownloadRepository | None = None,
        system_config: SystemConfig | None = None,
    ):
        self.progress = progress_helper or ProgressTracker()
        self.download_repo = download_repo or DownloadRepository()
        self._pipeline = search_pipeline
        self._system_config = system_config or SystemConfig()
        self._indexer_helper = indexer_helper
        self._site_cache = site_cache
        self._site_engine = site_engine
        self._site_config_repo = site_config_repo or IndexerSiteConfigRepositoryAdapter()
        self._client = None
        self._client_type = None
        self._clients: dict[str, _IIndexClient] = {}
        self._clients_lock = Lock()

    def _ensure_clients(self) -> None:
        with self._clients_lock:
            if self._clients:
                return
            clients: dict[str, _IIndexClient] = {}
            builtin = self.__build_class("builtin")
            if builtin:
                clients["builtin"] = builtin
            idx_config = self._system_config.get(SystemConfigKey.IndexerConfig) or {}
            for ctype in ("jackett", "prowlarr"):
                cfg = idx_config.get(ctype, {})
                if cfg.get("host") and cfg.get("api_key"):
                    client = self.__build_class(ctype, cfg)
                    if client:
                        clients[ctype] = client
            self._clients = clients

    def __build_class(self, ctype, conf=None):
        ctype_str = ctype.value if hasattr(ctype, "value") else ctype
        for cls in get_all_clients():
            try:
                if cls.match(ctype_str):
                    if ctype_str == "builtin":
                        return cls(
                            conf,
                            indexer_helper=self._indexer_helper,
                            site_cache=self._site_cache,
                            site_engine=self._site_engine,
                            download_repo=self.download_repo,
                        )
                    return cls(conf, download_repo=self.download_repo)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    def _filter_indexers(self, client, check=True, filter_args=None):
        """获取单个客户端的可用站点，第三方按 enabled 过滤。"""
        indexers = client.get_indexers(check=check)
        if client.client_id != "builtin":
            enabled_names = set(self._site_config_repo.list_enabled_names(source=client.client_id))
            indexers = [i for i in indexers if i.name in enabled_names]
        if filter_args and filter_args.get("site"):
            site_filter = filter_args.get("site")
            indexers = [i for i in indexers if i.name in site_filter]
        return indexers

    def search_by_keyword(self, key_word, filter_args, match_media, in_from):
        if not key_word:
            return []

        self._ensure_clients()
        if not self._clients:
            return []

        progress_key = ProgressKey.SubscribeSearch if in_from == SearchType.SUBSCRIBE else ProgressKey.Search

        # ---------- 扁平化所有 (client, indexer) 工作项 ----------
        work_items = []
        for client in self._clients.values():
            indexers = self._filter_indexers(client, check=True, filter_args=filter_args)
            for indexer in indexers:
                order_seq = 100 - int(getattr(indexer, "pri", 0))
                work_items.append((client, indexer, order_seq))

        if not work_items:
            log.error("没有配置索引器，无法搜索！")
            return []

        start_time = datetime.datetime.now()
        max_workers = min(len(work_items), 15)

        if filter_args and filter_args.get("site"):
            log.info(
                f"开始搜索 %s，站点：%s，并发数：%s ..."
                % (key_word, filter_args.get("site"), max_workers)
            )
        else:
            log.info(
                f"开始并行搜索 %s，工作项：%s，并发数：%s ..."
                % (key_word, len(work_items), max_workers)
            )

        # ---------- 阶段1：单层并发搜索，收集原始结果 ----------
        all_raw_results: list[dict] = []
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = {
                executor.submit(
                    client.search, order_seq, indexer, key_word, filter_args, match_media, in_from
                ): (client, indexer)
                for client, indexer, order_seq in work_items
            }
            completed = 0
            for future in as_completed(futures, timeout=120):
                client, indexer = futures[future]
                completed += 1
                pct = 10 + round(50 * (completed / len(futures)))
                self.progress.update(
                    ptype=progress_key,
                    value=pct,
                    text=f"站点搜索 {completed}/{len(futures)} 完成 ({pct}%)",
                )
                try:
                    result = future.result()
                    if result:
                        all_raw_results.extend(result)
                except Exception:
                    log.error(f"[Indexer]{client.client_id} 搜索 {indexer.name} 失败")
        finally:
            executor.shutdown(wait=False)

        # ---------- 阶段2：去重 + 统一批量识别和过滤 ----------
        pipeline_result = self._pipeline.process(
            all_results=self._dedup(all_raw_results),
            filter_args=filter_args,
            match_media=match_media,
            in_from=in_from,
            progress_key=progress_key,
        )

        end_time = datetime.datetime.now()
        log.info(
            f"搜索关键词 {key_word} 所有站点完成，"
            f"原始结果 {len(all_raw_results)} 条，有效资源数：{len(pipeline_result.results)}，"
            f"总耗时 {(end_time - start_time).seconds} 秒"
        )
        self.progress.update(
            ptype=progress_key,
            text=(
                f"搜索关键词 {key_word} 所有站点完成，"
                f"有效资源数：{len(pipeline_result.results)}，"
                f"总耗时 {(end_time - start_time).seconds} 秒"
            ),
        )

        return pipeline_result.results

    @staticmethod
    def _dedup(results: list[dict]) -> list[dict]:
        # builtin 来源优先：先按 source 排序，builtin 在前，再按 order_seq 保序
        ordered = sorted(
            results,
            key=lambda r: (0 if r.get("_indexer_source") == "builtin" else 1, r.get("_indexer_order", 0))
        )
        seen: set[tuple] = set()
        deduped: list[dict] = []
        for r in ordered:
            key = (r.get("title", ""), r.get("size", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped
```

**去重**：`_dedup()` 在进 `SearchPipeline` 前执行。key 为 `(title, size)` 组合。排序后 builtin 结果排在前面，确保同名站点冲突时保留 builtin 的完整配置。

**超时**：`as_completed(..., timeout=120)` 控制整体等待上限，单个 `future.result()` 不再单独设 timeout；异常或超时不阻塞其他索引器。

**进度**：进度条按扁平化工作项计算，单客户端与多客户端行为一致。

**线程安全**：`_ensure_clients()` 用 `Lock` 保护，避免多线程重复初始化。

**BuiltinIndexer 站点开关迁移**：`BuiltinIndexer.get_indexers(check=True)` 在过渡期保留 `UserIndexerSites` 过滤作为回退；`SiteCache.refresh()` 同步写入 `INDEXER_SITE_CONFIG` 后，`BuiltinIndexer` 改为优先按 `INDEXER_SITE_CONFIG.enabled` 过滤，旧字段仅作为一次性迁移数据源，不再参与运行时过滤。

### 3.1 `get_indexers()` 语义调整

多客户端后，保留 `SearchIndexer` 作为**默认搜索索引器**。`Indexer.get_client()` / `get_client_type()` / `get_indexers()` 保持现有语义：返回默认搜索索引器对应的客户端及其站点，确保旧调用方（如 `search_message_service.py`、`IndexerService.get_client_info()`）行为不变。

新增方法负责多索引器场景：

| 方法 | 返回值 | 用途 |
|------|--------|------|
| `Indexer.get_indexers(check=True)` | 默认搜索索引器的站点 | 兼容旧调用 |
| `Indexer.get_all_search_indexers()` | 所有已启用客户端的站点 | 多索引器搜索 |
| `Indexer.get_builtin_indexers(check=True)` | 仅 builtin 站点 | PT 管理功能 |
| `IndexerService.get_user_indexers()` | 默认搜索索引器的已启用站点 | 旧接口兼容 |
| `IndexerService.get_all_user_indexers()` | 所有索引器的已启用站点 | 订阅/搜索站点选择器 |

`POST /download/indexers` 改调 `IndexerService.get_all_user_indexers()`。

**索引器统计**：`Indexer.get_indexer_statistics()` 原按单客户端 `client_id` 查询。多客户端后改为聚合所有客户端，返回 dict 列表：

```python
def get_indexer_statistics(self):
    self._ensure_clients()
    stats = []
    for client in self._clients.values():
        rows = self.download_repo.get_indexer_statistics(client.get_client_id())
        for row in rows:
            stats.append({
                "indexer": row[0],
                "total": row[1],
                "fail": row[2],
                "success": row[3],
                "avg": row[4] or 0,
            })
    return stats
```

`IndexerService.get_indexer_statistics()` 同步调整，将 dict 列表转换为 `IndexerStatisticsDTO` 列表和图表 dataset。

### 3.2 索引器配置保存行为

当前 `IndexerConfigService.save_config()` 无论保存哪种索引器都会把 `SystemConfigKey.SearchIndexer` 设为当前保存的类型（`name`）。多索引器模式下，保存 Jackett/Prowlarr 配置**不应**改变当前默认搜索索引器，用户可能希望同时启用多个。

修改后：

```python
# 仅当显式选择“默认搜索索引器”时才写入 SearchIndexer
if data.get("set_default_indexer"):
    self._system_config.set(SystemConfigKey.SearchIndexer, name)
```

前端索引器配置页需增加“设为默认搜索索引器”开关；保存 Jackett/Prowlarr 配置时默认不勾选，仅更新 `IndexerConfig`。保存 builtin 配置时保持现有行为（可视为默认就是 builtin）。

### 4. 搜索结果注入

当前 `_IIndexClient.search()`（`src/app/indexer/client/_base.py:107`）对所有类型索引器都注入了 `_indexer_name = indexer.name`。

- builtin 的 `indexer.name` = JSON 中的 `"M-Team"`、`"TNode"` 等
- Jackett 的 `indexer.name` = API 返回的 `name` 字段（如 `"kickass"`, `"1337x"`）
- Prowlarr 的 `indexer.name` = API 返回的 `indexerName` 字段

**不需要额外改动**。`_indexer_name` 已经正确携带了各索引器的站点名。

只需追加 `_indexer_source` 标记来源，但不影响核心流程：

```python
# _base.py:107 追加一行
item["_indexer_source"] = self.client_type or self.client_id
```

`BuiltinIndexer.search()` 重写了父类 `search()`，因此也要在 `src/app/indexer/client/builtin.py:244-246` 的注入循环中追加同一字段：

```python
for item in result_array:
    item["_indexer_name"] = indexer.name
    item["_indexer_order"] = order_seq
    item["_indexer_public"] = getattr(indexer, "public", False)
    item["_indexer_source"] = self.client_type or self.client_id
```

**索引器统计补充**：当前 `BuiltinIndexer.search()` 会写入 `INDEXER_STATISTICS`，而 `_base.py` 默认实现不会。多客户端聚合统计需要第三方来源也有数据，因此在 `_base.py` 默认 `search()` 中追加统计写入（与 `BuiltinIndexer` 相同字段），避免聚合结果只含 builtin。

### 5. 下载设置解析

`pipeline._stage_resolve()` 中添加对 `INDEXER_SITE_CONFIG` 的查询。

当前优先级链（`src/app/downloader/pipeline.py:270-279`）：

```
1. 显式 download_setting 参数        → 直接使用
2. media_info.site                  → SiteCache.get_site_download_setting(site)
3. "-2" 特殊值                       → download_attr = {}
4. 以上都无                          → ClientFactory.default_download_setting_id
```

修改后在第 2 步增加 `INDEXER_SITE_CONFIG` 回退：

```python
if not download_setting and media_info.site:
    # 先查内置 SiteCache（兼容旧行为）
    download_setting = self._sites.get_site_download_setting(media_info.site)
    # 查不到再查 INDEXER_SITE_CONFIG
    if not download_setting:
        download_setting = self._site_config_repo.get_download_setting(media_info.site)
```

`IndexerSiteConfigRepositoryAdapter.get_download_setting()`：

```python
def get_download_setting(self, site_name: str) -> str | None:
    row = self._repo.get_by_name(site_name)
    if row and row.enabled and row.download_setting is not None:
        return str(row.download_setting)
    return None
```

只有当 `enabled=1` 且 `download_setting` 不为 NULL 时才返回。

### 6. 站点列表合并

`SiteService.get_sites()` 在**非 RSS/刷流/统计过滤**时合并第三方站点；`basic` 参数决定返回格式：

- `basic=True`（搜索站点选择器）：返回 `{id, name, source, third_party}` 简单列表。
- `basic=False`（站点管理页）：返回完整站点字典，第三方站点用默认值填充 PT 相关字段。

```python
def get_sites(self, rss=False, brush=False, statistic=False, basic=False):
    # RSS/刷流/统计场景只返回 builtin 站点
    if rss or brush or statistic:
        return self._sites.get_sites(rss=rss, brush=brush, statistic=statistic, public=True)

    builtin = self._sites.get_sites(public=True)
    third_party_rows = self._indexer_site_repo.list_all(
        source_ne="builtin", enabled=True
    )

        if basic:
            merged = {s["name"]: {"id": s["id"], "name": s["name"], "source": "builtin"} for s in builtin}
            for row in third_party_rows:
                if row.site_name not in merged:
                    merged[row.site_name] = {
                        "id": str(row.id or 0),
                        "name": row.site_name,
                        "source": row.source,
                        "third_party": True,
                    }
            return list(merged.values())


    # 完整模式：站点管理页
    merged = {s["name"]: {**s, "source": "builtin"} for s in builtin}
    for row in third_party_rows:
        if row.site_name not in merged:
            merged[row.site_name] = _third_party_site_dict(row)
    return list(merged.values())


def _third_party_site_dict(row) -> dict:
    return {
        "id": row.id,
        "name": row.site_name,
        "pri": 0,
        "source": row.source,
        "third_party": True,
        "download_setting": row.download_setting,
        "enabled": bool(row.enabled),
        "public": bool(row.public),
        # 以下字段内置站点有、第三方站点无，填充默认值保证前端兼容
        "rssurl": "", "signurl": "", "cookie": "",
        "api_key": "", "bearer_token": "", "api_key_header": None,
        "headers": None, "rule": None,
        "rss_enable": False, "brush_enable": False,
        "statistic_enable": False, "uses": [],
        "ua": "", "parse": False, "unread_msg_notify": False,
        "chrome": False, "proxy": False, "subtitle": False,
        "limit_interval": None, "limit_count": None,
        "limit_seconds": None, "strict_url": "",
        "note": {},
    }
```

**内置站点优先**：当 `site_name` 相同时，builtin 行覆盖第三方行。确保有站点 JSON 定义的站点保留完整功能（数据刷新、签到、做种统计等）。

**注意**：第三方站点的 `id` 在简单模式下使用 `INDEXER_SITE_CONFIG.id`，在完整模式下也使用 `INDEXER_SITE_CONFIG.id`，与 builtin 站点的 `CONFIG_SITE.id` 不是同一命名空间。前端对第三方站点操作时应以 `name` 和 `source` 为标识，不要跨源比较 `id`。

### 7. 索引器配置 API 扩展

`POST /system/indexers`（`src/api/routers/system.py:380`）需要返回第三方站点列表，供前端展示和管理：

```python
@router.post("/indexers", ...)
def get_indexers(...):
    # 现有逻辑：返回 builtin indexer 列表 + config
    ...

    # 新增：返回 INDEXER_SITE_CONFIG 中所有第三方站点
    third_party_sites = idx_svc.get_third_party_sites()
    # 格式: [{id, site_name, source, download_setting, enabled}, ...]

    return success(data={
        ...现有字段...,
        "third_party_sites": third_party_sites,
    })
```

### 8. 新增 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/sites/indexer-config/update` | 更新单个站点的 `enabled` / `download_setting` |
| POST | `/sites/indexer-config/sync` | 手动触发指定索引器的站点同步 |
| POST | `/sites/indexer-config/batch` | 批量更新（索引器配置保存页的"同步站点"按钮） |

### 9. 订阅搜索站点选择器

已在 4.1.8 中修复：`POST /download/indexers` 改为调用 `get_user_indexers()`，随当前激活索引器返回站点列表。

多索引器后需要改为**同时返回所有索引器的已启用站点**：

```python
# IndexerService 新增方法
def get_all_user_indexers(self) -> list[UserIndexerDTO]:
    """返回所有已配置索引器的已启用站点，多索引器合并"""
    rows = self._site_config_repo.list_all(enabled=True)
    return [UserIndexerDTO(id=row.id or 0, name=row.site_name) for row in rows]
```

`POST /download/indexers` 改调此方法。

### 10. 前端

| 页面 | 改动 |
|------|------|
| 站点列表 | 新增 `source` 和 `third_party` 列。`third_party=True` 时：只显示下载设置下拉 + 开关，隐藏编辑/测试连接/刷新数据/删除按钮 |
| 索引器配置 | 保存 Jackett/Prowlarr 后自动调 `/sites/indexer-config/sync` 同步站点列表 |
| 订阅编辑 | 搜索站点下拉调用 `get_all_user_indexers()`，合并所有索引器的站点 |
| 站点列表（内置） | 页面加载时仍调 `POST /sites`，含合并后的第三方站点 |

## 备选方案

### 方案 B: 复用 `CONFIG_SITE` 表

为第三方站点创建 `CONFIG_SITE` 行，`NOTE` 存配置。

**拒绝理由**：
- `SiteEngine._load()` 遍历 `config/sites/` 目录生成 `SiteDefinition`。`CONFIG_SITE` 行无对应 JSON → `SiteCache._build_site_info()` 无法解析 `api_key_header`/`strict_url`
- RSS 签到、做种统计、站点数据刷新等任务会遍历 `CONFIG_SITE`，对第三方站点执行会失败
- `SITE_STATISTICS_HISTORY`、`SITE_USER_INFO_STATS` 会产生无效数据

### 方案 C: 第三方站点不在站点列表显示

只作为搜索来源，不进入前端管理页。

**拒绝理由**：无法单独开关、无法配下载设置——丧失内置站点已有的能力。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 站点名不一致（Jackett 用 `MTeam`，builtin 用 `M-Team`） | 后续在表中加 `aliases` 字段，搜索匹配时做模糊查找；初期手动关联 |
| 第三方离线时站点列表变动 | Repository `upsert` 只更新/插入不删除，离线时不丢失已配置站点 |
| 多索引器并行增加耗时 | 单层 `ThreadPoolExecutor` 扁平化 `(client, indexer)` 工作项；`as_completed(timeout=120)`，单索引器失败不阻塞 |
| 去重 key `(title, size)` 不精确 | 排序后 builtin 优先；后续加 `info_hash` 作为备选 key；误去重比重复更差，松匹配优先 |
| `SearchIndexer` 单值与多客户端矛盾 | 保存 Jackett/Prowlarr 配置时不再默认覆盖 `SearchIndexer`，新增“设为默认搜索索引器”开关 |
| 嵌套 ThreadPoolExecutor 死锁 | 禁止两层 executor；所有搜索任务扁平化到单层线程池 |
| Prowlarr 站点列表 API 不稳定 | `indexerstats` 接口用于现有实现；若后续返回字段不全，切换到 `/api/v1/indexer` 并补 `X-Api-Key` 头 |
| 数据库 upsert 方言差异 | Repository 层封装 dialect 无关 upsert，业务层不写方言 SQL |

## 实施计划

### Phase 1: 数据库 + 仓库 + Adapter
- [x] `INDEXER_SITE_CONFIG` SQLAlchemy ORM 模型
- [x] `src/app/domain/interfaces/indexer_site_config_repo.py` (`IIndexerSiteConfigRepository`)
- [x] `src/app/db/repositories/indexer_site_config_repository.py` (原始 ORM 操作)
- [x] `src/app/db/repositories/indexer_site_config_repo_adapter.py` (适配领域接口)

### Phase 2: 写入链路
- [x] `initializer.py` 启动时调用 `IndexerSiteConfigRepositoryAdapter.migrate_from_user_indexer_sites()` 完成一次性迁移
- [x] `SiteCache.refresh()` 中扫描 builtin 站点名 → Adapter `upsert`（保留现有 enabled/download_setting）
- [x] `IndexerConfigService.save_config()` 保存后拉取第三方站点 → 批量 `upsert`；保存 Jackett/Prowlarr 时不默认覆盖 `SearchIndexer`
- [x] `IndexerService` 新增 `get_all_user_indexers()`、`get_third_party_sites()`
- [x] DI 注册 `IIndexerSiteConfigRepository` → `IndexerSiteConfigRepositoryAdapter`，并注入 `Indexer` / `SiteService` / `DownloadPipeline` / `SiteCache`

### Phase 3: 搜索链路
- [x] `Indexer._ensure_clients()` 改为多客户端 dict + `Lock`
- [x] `Indexer.search_by_keyword()` 扁平化工作项 + 单层 `ThreadPoolExecutor` + `_dedup()`
- [x] `Indexer.get_indexers()` / `get_client()` / `get_client_type()` 保持默认搜索索引器语义
- [x] 新增 `Indexer.get_all_search_indexers()` 供多索引器搜索使用
- [x] `IndexerService.get_indexer_statistics()` 聚合多客户端统计
- [x] `pipeline._stage_resolve()` 增加 `INDEXER_SITE_CONFIG` 查询回退

#### Phase 3.1: Jackett / Prowlarr 重构

多客户端模式下需要修复以下问题：

**问题 1: `_client_config` 类变量 → 实例变量**

jackett.py:11 `_client_config = {}`，prowlarr.py:11 相同。类变量被所有实例共享，多客户端并发时互相覆盖。

```python
# jackett.py / prowlarr.py: __init__
# before
class Jackett(_IIndexClient):
    _client_config = {}  # 类变量，多实例共享

# after
class Jackett(_IIndexClient):
    _client_config: dict  # 类型声明，实例变量

    def __init__(self, config=None):
        super().__init__()
        self._client_config = config or {}  # 改为实例变量赋值
        self._password = None  # jackett 特有
        self._refresh()
```

**问题 2: `_password` 类变量 → 实例变量**

jackett.py:46 `_password = None`，同上。

```python
# jackett.py
# before
_password = None

def __init__(self, ...):
    ...
    self._refresh()

# after
def __init__(self, config=None):
    super().__init__()
    self._password = None
    self._client_config = config or {}
    self._refresh()
```

**问题 3: 去掉 `SystemConfig` 兜底**

jackett.py:53-57, prowlarr.py:43-48。构造函数 `config` 为 None 时兜底读 `SystemConfig`。多客户端模式下由 `Indexer._ensure_clients()` 显式传入配置，不再需要兜底。

```python
# before
def __init__(self, config=None, system_config=None):
    ...
    if config:
        self._client_config = config
    else:
        _system_config = system_config or SystemConfig()
        indexer_config = _system_config.get(SystemConfigKey.IndexerConfig) or {}
        self._client_config = indexer_config.get("jackett") or {}

# after
def __init__(self, config=None):
    super().__init__()
    self._password = None
    self._client_config = config or {}
    self._refresh()
```

**问题 4: 搜索结果注入 `_indexer_source` 与统计**

`_base.py:107` 已注入 `_indexer_name`，追加 `_indexer_source` 标记来源索引器，并补充统计写入：

```python
# _base.py 注入循环追加
for item in result_array:
    item["_indexer_name"] = indexer.name
    item["_indexer_order"] = order_seq
    item["_indexer_public"] = getattr(indexer, "public", False)
    item["_indexer_source"] = self.client_type or self.client_id  # "builtin" / "jackett" / "prowlarr"

# 统计写入（第三方客户端走默认实现）
if self.download_repo:
    try:
        self.download_repo.insert_indexer_statistics(
            indexer=indexer.name,
            itype=self.client_type or self.client_id,
            seconds=int(_),
            result="success" if result_count > 0 else "fail",
        )
    except Exception as e:
        log.warn(f"[Indexer]写入统计失败: {e!s}")
```

**涉及文件**: `jackett.py`、`prowlarr.py`、`_base.py`、`builtin.py`。

### Phase 4: 站点列表
- [x] `SiteService.get_sites()` 合并 builtin + 第三方
- [x] `POST /sites` 返回合并列表
- [x] 新增 `/sites/indexer-config/update`、`/sites/indexer-config/sync`、`/sites/indexer-config/batch`

### Phase 5: 前端
- [x] 站点列表页增加 `source` / `third_party` 列，区分操作（`frontend/apps/nexus-media/src/views/site/list/components/SiteCard.vue`）
- [x] 站点列表页对第三方站点显示启用开关 + 下载设置下拉，隐藏编辑/测试/删除（`SiteCard.vue` + `index.vue`）
- [x] 索引器配置保存后自动同步站点（`frontend/apps/nexus-media/src/views/service/indexer/index.vue`）
- [x] 索引器配置保存 Jackett/Prowlarr 时增加“设为默认搜索索引器”开关
- [x] 新增前端 API：`updateIndexerSiteConfigApi`、`syncIndexerSitesApi`、`batchUpdateIndexerSiteConfigApi`（`frontend/apps/nexus-media/src/api/modules/site.ts`）


## 验证标准

- [x] `INDEXER_SITE_CONFIG` 表创建成功
- [x] 配置 Jackett 后表中出现对应行（`source='jackett'`）
- [x] `POST /api/sites` 返回含 `third_party=True` + `source` 字段的站点
- [x] builtin + Jackett 并发搜索均返回结果
- [x] 同一 PT 站的搜索结果已去重
- [x] 设第三方站点 `download_setting` 后下载走配置的下载器
- [x] 设第三方站点 `enabled=0` 后搜索结果不含该站
- [x] `uv run ruff check .` 通过
- [x] `uv run pyright src/ tests/` 通过
- [x] `uv run pytest tests/ -v` 全部通过
- [x] 新增测试覆盖 `IndexerSiteConfigRepository` CRUD
- [x] 新增测试覆盖 `SiteService.get_sites()` 合并逻辑
- [x] 新增测试覆盖 `Indexer._dedup()` 去重（含 builtin 优先场景）

> 注：已补充 Repository CRUD、`SiteService.get_sites()` 合并逻辑和 `Indexer._dedup()` 单元测试。
