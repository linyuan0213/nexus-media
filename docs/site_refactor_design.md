# 站点管理重构设计文档

## 1. 现状与问题

### 1.1 站点定义分散

站点定义分布在三个层面：

| 层面 | 存储 | 格式 | 内容 |
|------|------|------|------|
| 索引规则 | `config/sites.dat` | pickle 二进制 | 搜索 URL、类别映射、HTML 选择器 |
| 用户配置 | `CONFIG_SITE` 数据库 | SQL | URL、Cookie、优先级、代理 |
| 特殊逻辑 | Python 代码 20+ 文件 | 硬编码 | 下载链接、字幕、详情页、用户信息 |

### 1.2 站点特殊逻辑散落

`m-team` / `yemapt` 硬编码引用出现在 20+ 个文件：

| 模块 | 文件 | 问题 |
|------|------|------|
| 下载 | `downloader/pipeline.py:358` | `_get_download_url()` 硬编码 m-team/yemapt |
| 下载策略 | `services/download_strategies.py` | 4 处 `if 'm-team' in url` |
| 站点管理 | `sites/sites.py` | 6 处 URL 重写 |
| 站点配置 | `sites/siteconf.py` | `URL_DETAIL_TEMPLATES` dict 硬编码 |
| 字幕 | `sites/site_subtitle.py` | 8 处 m-team 字幕 API |
| 刷流 | `services/brush_core.py` | site_key 硬编码 |
| 搜索 | `indexer/client/builtin.py` | 5 种专用爬虫分发 |
| 工具 | `utils/string_utils.py` | URL 特殊处理 |

### 1.3 核心问题

1. **无统一入口**：每个功能都要判断 `if 'm-team' in url`
2. **sites.dat 不可版本化**：Pickle 二进制，git diff 无效
3. **搜索引擎和配置捆绑**：每种站点类型需单独编写 Python 爬虫类
4. **API 和 HTML 站点混杂**：搜索逻辑和站点属性合在一起

---

## 2. 设计目标

1. **统一站点定义**：结构化 JSON，存放在 `nas-tools-sites` 仓库
2. **区分 API/HTML 接口**：定义标准化的 Site Schema
3. **统一特殊逻辑**：下载链接、字幕、用户信息整合到站点定义
4. **可扩展**：新站点只需 JSON 配置，不需 Python 代码

---

## 3. 架构

### 3.1 目录结构

```
nas-tools-sites/
├── schema/
│   ├── site-api.schema.json       # API 站点 schema
│   └── site-html.schema.json      # HTML 站点 schema
├── api/
│   ├── mteam.json                 # M-Team
│   ├── yemapt.json                # YemaPT
│   ├── rousi.json                 # Rousi
│   ├── tnode.json                 # TNode
│   └── torrentleech.json          # TorrentLeech
└── html/                          # HTML 站点（从 sites.dat 迁移）
    ├── hd4fans.json
    └── ...
```

### 3.2 核心模型

```python
@dataclass
class SiteDefinition:
    id: str                        # 唯一标识，如 "mteam"
    name: str                      # 显示名称
    domain: str                    # 主域名
    encoding: str = "UTF-8"
    public: bool = False
    api: Optional[SiteApiConfig] = None
    html: Optional[SiteHtmlConfig] = None
    download: Optional[DownloadConfig] = None
    subtitle: Optional[SubtitleConfig] = None
    userinfo: Optional[UserInfoConfig] = None

class SiteEngine:
    """统一站点引擎"""
    def resolve_download_url(self, page_url: str) -> Optional[str]: ...
    def create_searcher(self, site: SiteDefinition) -> SiteSearcher: ...
    def get_site(self, url: str) -> Optional[SiteDefinition]: ...
```

### 3.3 API 站点 Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "API Site Definition",
  "type": "object",
  "required": ["id", "name", "domain", "api"],
  "properties": {
    "id": {"type": "string"},
    "name": {"type": "string"},
    "domain": {"type": "string"},
    "api": {
      "type": "object",
      "properties": {
        "base_url": {"type": "string"},
        "auth": {
          "type": "object",
          "properties": {
            "type": {"enum": ["cookie", "api_key", "bearer"]},
            "header_name": {"type": "string"}
          }
        },
        "endpoints": {
          "search": {"$ref": "#/definitions/endpoint"},
          "detail": {"$ref": "#/definitions/endpoint"},
          "download": {"$ref": "#/definitions/endpoint"}
        }
      }
    },
    "download": {"$ref": "#/definitions/download_config"},
    "subtitle": {"$ref": "#/definitions/subtitle_config"}
  }
}
```

### 3.4 示例：mteam.json

```json
{
  "id": "mteam",
  "name": "M-Team",
  "domain": "api.m-team.io",
  "api": {
    "base_url": "https://api.m-team.io/api",
    "auth": {"type": "cookie"},
    "endpoints": {
      "search": {
        "method": "POST",
        "path": "/torrent/search",
        "body": {"mode": "normal", "keyword": "{keyword}", "pageSize": 100},
        "response": {"total_key": "data.total", "items_key": "data.data"}
      },
      "detail": {
        "method": "POST",
        "path": "/torrent/detail",
        "body": {"id": "{tid}"}
      }
    }
  },
  "download": {
    "type": "api",
    "method": "POST",
    "path": "/api/torrent/genDlToken",
    "body": {"id": "{tid}"},
    "response_key": "data"
  },
  "subtitle": {
    "type": "api",
    "list": {"method": "GET", "path": "/api/subtitle/list", "params": {"torrentId": "{tid}"}},
    "genlink": {"method": "GET", "path": "/api/subtitle/genlink"},
    "download": {"method": "GET", "path": "/api/subtitle/dlV2"}
  }
}
```

### 3.5 用户配置与站点定义分离

```
nas-tools-sites/                用户数据库
┌──────────────┐               ┌──────────────────┐
│ mteam.json   │               │ CONFIG_SITE       │
│ ├─ search    │               │ ├─ COOKIE         │
│ ├─ download  │──────────────│ ├─ PRI            │
│ └─ subtitle  │    匹配        │ ├─ NOTE(proxy等)  │
└──────────────┘               │ └─ INCLUDE        │
                               └────────┬─────────┘
                                        │
                               ┌────────▼─────────┐
                               │   SiteEngine      │
                               │   (运行时合并)     │
                               └──────────────────┘
```

---

## 4. 下载链接策略

将散落的 `if 'm-team' in url` 替换为声明式配置：

| 站点 | 当前实现 | 新配置 |
|------|----------|--------|
| m-team | `_get_download_url` POST `/api/torrent/genDlToken` | `download.type=api` |
| yemapt | `_get_download_url` GET key → URL 拼接 | `download.type=api_chained` |
| rousi | 字符串拼接 `/api/v1/torrents/{uuid}/download` | `download.type=template` |
| HTML | CSS 选择器 `a[href*="download.php"]` | 从 torrents 字段 |

---

## 5. 实施路径

### Phase 1: 建模 — `app/sites/engine.py`
- `SiteEngine` 类：加载 JSON → 匹配 URL → 提供功能
- `SiteSearcher` 接口：`ApiSiteSearcher` / `HtmlSiteSearcher`

### Phase 2: 迁移 API 站点
- 将 5 个专用爬虫的逻辑编码为 JSON 配置
- 到 `nas-tools-sites/api/` 目录

### Phase 3: 统一调用点
- 替换 `pipeline.py:_get_download_url()` → `engine.resolve_download_url()`
- 替换 `download_strategies.py` 的所有 `if 'm-team' in url`
- 替换 `siteconf.py` 的 `URL_DETAIL_TEMPLATES`
- 移除 `app/indexer/client/_mteam.py`、`_yemapt.py` 等专用爬虫

### Phase 4: HTML 站点迁移
- 将 `sites.dat` indexer 部分导出为 JSON

---

## 6. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| **新增** | `app/sites/engine.py` | SiteEngine 核心 |
| **新增** | `app/sites/searchers.py` | ApiSiteSearcher |
| **修改** | `app/downloader/pipeline.py` | 移除 `_get_download_url` |
| **修改** | `app/services/download_strategies.py` | 移除硬编码判断 |
| **修改** | `app/sites/siteconf.py` | 委托 engine |
| **修改** | `app/sites/site_subtitle.py` | 委托 engine |
| **修改** | `app/sites/sites.py` | 整合 engine |
| **修改** | `app/indexer/client/builtin.py` | 用 engine 创建 searcher |
| **删除** | `app/indexer/client/_mteam.py` | → JSON 驱动 |
| **删除** | `app/indexer/client/_yemapt.py` | → JSON 驱动 |
| **删除** | `app/indexer/client/_rousi.py` | → JSON 驱动 |
| **删除** | `app/indexer/client/_tnode.py` | → JSON 驱动 |
