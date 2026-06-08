# ADR-013: 站点模块 Sites 类迁移到领域驱动架构

## Status

Proposed / Design Complete

## Date

2026-06-08

## Context

### 当前问题

`app.sites.sites.Sites` 类（以下简称旧 `Sites`）是项目早期的核心类，承担了数据访问、内存缓存、业务逻辑三重职责，当前存在以下问题：

1. **职责混乱**：23 个方法混合了 CRUD、缓存管理、业务逻辑（连通性测试、限流检查、图标解析）、数据转换
2. **缓存同步缺失**：`SiteService` 已迁移到新的领域实体仓库（`SiteRepositoryAdapter`），但写操作后不刷新旧 `Sites` 的内存缓存，导致配置修改后需重启才能生效
3. **无法测试**：`Sites` 是 DI Singleton，内部直接操作 ORM 和全局状态，难以 Mock
4. **重复实现**：新旧两套 CRUD 并存（`Sites.add/update/delete` 和 `SiteRepositoryAdapter.insert/update/delete`）

### 旧 Sites 方法分类

```
Sites (23 个方法)
├── 缓存管理: __init__, _refresh
├── 图标管理: init_favicons, get_site_favicon, _resolve_favicon, _favicon_fallback_url
├── 查询方法: get_sites, get_sites_by_suffix, get_sites_by_name, get_max_site_pri,
│           get_site_dict, get_site_names, get_site_download_setting, check_ratelimit
├── 业务方法: test_connection
├── 工具方法: __get_site_note_items, _rate_limit_val (静态)
└── CRUD方法: add_site, update_site, delete_site, update_site_cookie, update_site_note,
             get_site_note_by_id
```

### 引用现状

旧 `Sites` 被 30+ 处直接引用（`container.sites()`），分布在：
- `app/services/` — 业务服务（brush, subscribe, download, search 等）
- `app/sites/` — 子模块（site_userinfo, site_subtitle, site_cookie）
- `app/indexer/` — 索引器
- `app/downloader/` — 下载器
- `app/plugin_framework/builtin_plugins/` — 插件

## 目标

- 消除新旧两套 CRUD 的重复
- 解耦缓存、数据访问、业务逻辑三层
- 写操作后缓存自动刷新，无需重启
- 保持向后兼容的查询接口（`get_sites` 等）
- 所有调用方逐步迁移到新体系

## 决策

### 架构：三层拆分

```
┌─────────────────────────────────────────────────────────────┐
│  调用方 (30+ 处)                                             │
│  container.site_cache() │ container.site_resolver()          │
├─────────────────────────────────────────────────────────────┤
│  SiteCache (缓存层)           SiteResolver (业务层)          │
│  ├─ 内存索引 (_site_by_ids)   ├─ test_connection()          │
│  ├─ get_sites(...)            ├─ (未来扩展)                  │
│  ├─ check_ratelimit()                                        │
│  └─ refresh()                                                │
├─────────────────────────────────────────────────────────────┤
│  SiteFaviconService (图标服务)                               │
│  ├─ get_favicon(site_name)                                   │
│  └─ refresh()                                                │
├─────────────────────────────────────────────────────────────┤
│  ISiteRepository (数据访问层)                                │
│  ├─ SiteRepositoryAdapter (当前实现)                         │
│  ├─ get_by_id(), list_all(), insert(), update(), delete()   │
│  └─ update_cookie_ua()                                       │
└─────────────────────────────────────────────────────────────┘
```

### 组件设计

#### 1. SiteCache — 内存缓存层

职责：替代旧 `Sites` 的缓存和查询能力

- 从 `ISiteRepository.list_all()` 构建内存索引
- 提供 `get_sites()`（支持 rss/brush/statistic/public/siteid/siteurl 过滤）
- 提供 `get_site_by_id()`、`get_site_by_url()`
- 提供 `get_site_names()`、`get_site_dict()`、`get_max_pri()`
- 提供 `check_ratelimit()`（委托给 `SiteRateLimiterService`）
- 提供 `refresh()` — 重建所有索引
- **非 Singleton**：每次 `container.site_cache()` 返回新实例，但底层共享同一缓存

关键设计：缓存刷新由写操作触发

```python
# SiteService 写操作后统一刷新
class SiteService:
    def update_site(self, data):
        self._repo.update(entity)
        self._cache.refresh()  # 触发缓存重建
```

#### 2. SiteResolver — 业务逻辑层

职责：替代旧 `Sites` 的 `test_connection` 等业务方法

- `test_connection(site_id)` — 从 `SiteCache` 获取配置，调用 `SiteEngine`
- 未来可扩展：站点健康检查、批量测试等

#### 3. SiteFaviconService — 图标服务

职责：替代旧 `Sites` 的图标相关方法

- `get_favicon(site_name)` — 从缓存/数据库/SiteEngine 三级查找
- `get_all_favicons()` — 返回全部图标映射
- `refresh()` — 重建图标缓存

#### 4. ISiteRepository — 数据访问层（已有）

`SiteRepositoryAdapter` 已是当前实现，无需改动。唯一需要增加的是：

- 写操作后自动触发缓存刷新（通过 `SiteService` 统一处理，不在仓库层引入事件耦合）

### 迁移策略

#### Phase 1: 基础设施（创建新组件）

1. 创建 `app.sites.site_cache.SiteCache`
2. 创建 `app.sites.site_resolver.SiteResolver`
3. 创建 `app.sites.site_favicon_service.SiteFaviconService`
4. 注册到 DI Container

#### Phase 2: 替换核心调用方

按依赖深度从浅到深：

1. `SiteService` — 核心服务，优先替换
2. `app/sites/site_userinfo.py` — 直接使用 `get_sites()`
3. `app/sites/site_subtitle.py` — 直接使用 `get_sites()`
4. `app/sites/site_cookie.py` — 直接使用 `get_sites()`
5. `app/services/brush/` — 大量使用 `get_sites()`
6. `app/services/subscribe/` — 使用 `get_site_names()` 等
7. `app/services/download_core.py` — 使用 `get_sites()`
8. `app/indexer/client/builtin.py` — 使用 `get_sites()`
9. `app/downloader/pipeline.py` — 使用 `get_sites()`
10. `app/plugin_framework/builtin_plugins/` — 插件中使用

#### Phase 3: 清理

1. 从 DI Container 移除 `sites` provider
2. 删除旧 `Sites` 类
3. 更新 `SiteService` 删除旧引用

### 接口兼容性

`SiteCache.get_sites()` 返回 `dict` 列表，与旧 `Sites.get_sites()` 格式完全一致，调用方无需修改返回值的消费逻辑。

```python
# 旧调用
site = container.sites().get_sites(siteid=1)

# 新调用
site = container.site_cache().get_sites(siteid=1)
# site 格式完全相同
```

### 缓存刷新机制

**方案 A：SiteService 显式刷新（推荐）**

```python
class SiteService:
    def __init__(self, ...):
        self._cache = cache or container.site_cache()

    def update_site(self, data):
        self._repo.update(entity)
        self._cache.refresh()  # 立即刷新
```

优点：简单、无事件耦合、可预测
缺点：需要每个写操作都手动调用

**方案 B：事件驱动（备选）**

写操作发布 `site.changed` 事件，`SiteCache` 监听并刷新。

当前采用方案 A，因为项目写操作入口唯一（都在 `SiteService`），手动刷新足够且更可控。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 迁移过程中功能回退 | 高 | Phase 2 按模块逐个替换，每步验证 |
| 缓存刷新遗漏导致数据不一致 | 中 | SiteService 作为唯一写入口，强制刷新 |
| 性能退化（缓存重建频率） | 低 | 缓存重建是内存操作，< 10ms |
| 插件调用点遗漏 | 中 | 全局搜索 `container.sites()` 确保无遗漏 |

## 实施计划

### Phase 1: 基础设施
- [ ] Task 1: 创建 `SiteCache` 缓存层
- [ ] Task 2: 创建 `SiteResolver` 业务层
- [ ] Task 3: 创建 `SiteFaviconService` 图标服务
- [ ] Task 4: 注册到 DI Container，运行 ruff + pyright

### Phase 2: 替换调用方
- [ ] Task 5: `SiteService` + API Router 迁移
- [ ] Task 6: `app/sites/` 子模块迁移
- [ ] Task 7: `app/services/brush/` 迁移
- [ ] Task 8: `app/services/subscribe/` 迁移
- [ ] Task 9: `app/services/download_core.py` + `downloader/pipeline.py` 迁移
- [ ] Task 10: `app/indexer/` 迁移
- [ ] Task 11: 插件迁移

### Phase 3: 清理
- [ ] Task 12: 删除旧 `Sites` 类
- [ ] Task 13: 更新 DI Container，移除旧 provider
- [ ] Task 14: 全局验证（ruff + pyright + 搜索残留引用）

## 验证标准

- [ ] `uv run ruff check .` 通过
- [ ] `uv run pyright src/ tests/` 通过
- [ ] 全局搜索 `container.sites()` 无残留
- [ ] 全局搜索 `from app.sites.sites import Sites` 无残留
- [ ] 站点配置修改后无需重启即可生效
- [ ] 站点连通性测试功能正常
