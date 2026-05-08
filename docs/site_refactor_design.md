# 站点管理重构设计文档

## 1. 现状与问题

### 1.1 站点定义分散

当前站点配置散落在三个层面：

| 层面 | 存储位置 | 格式 | 内容 |
|------|----------|------|------|
| 索引规则 | `config/sites.dat` | pickle 二进制 | 搜索URL、类别映射、HTML选择器 |
| 用户配置 | `CONFIG_SITE` 数据库表 | SQL | URL、Cookie、优先级、代理、功能开关 |
| 特殊逻辑 | Python 代码 20+ 文件 | 硬编码 | 下载链接、字幕、详情页、用户信息 |

### 1.2 站点特殊逻辑散落 — 34 处硬编码

搜索 `m-team`/`yemapt`/`rousi` 等站点名，在 **12 个文件** 中发现 **34 处硬编码**：

| 分类 | 文件 | 行号 | 模式 | 说明 |
|------|------|------|------|------|
| **爬虫分发** | `builtin.py` | 174-200 | `if parser == "MteamSpider"` 等 | 7 种专用爬虫的 if/elif 链 |
| | `builtin.py` | 247-262 | 同上（`list()` 方法） | 完全重复的分发逻辑 |
| **URL 重写** | `sites.py` | 345-358 | `if '1ptba'/'fsm'/'yemapt' in url` | 连接测试 URL 拼接 |
| | `sites.py` | 362-383 | `if 'm-team' in url` POST | M-Team 用 API 而非 GET |
| | `site_userinfo.py` | 80-95 | `if 'fsm'/'yemapt' in url` | 用户信息 URL 重写 |
| **下载链接** | `download_strategies.py` | 203,271 | `if 'm-team' in url` | 4 处强制重解析下载链接 |
| **详情页模板** | `siteconf.py` | 87-94 | `URL_DETAIL_TEMPLATES` 字典 | 6 个站点的硬编码模板 |
| | `siteconf.py` | 169-191 | `if 'm-team' in torrent_url` | M-Team 专用属性检查 |
| **字幕下载** | `site_subtitle.py` | 46-267 | `if 'm-team' in page_url` | 整个 `_download_mteam_subtitle` 方法 |
| **刷流去重** | `brush_repository.py` | 216-228 | `if 'm-team'/'yemapt' in enclosure` | TID 去重替代 URL 去重 |
| **域名归一** | `cookiecloud/plugin.py` | 185,246 | `if 'm-team' in domain_url` | 子域名归一化 |
| **签到** | `autosignin/plugin.py` | 280,353 | `if '1ptba'/'m-team' in url` | 签到 URL 特殊处理 |

### 1.3 专用爬虫类（7 个）

每个 API 站点都有独立的 Python 爬虫类，包含完整的 API 端点、参数格式、响应解析：

| 爬虫类 | 站点 | API 端点 | 认证方式 | 行数 |
|--------|------|----------|----------|------|
| `MteamSpider` | M-Team | `/api/torrent/search` | x-api-key | 128 |
| `YemaPTSpider` | YemaPT | `/api/torrent/fetchCategoryOpenTorrentList` | Cookie | 115 |
| `RousiSpider` | Rousi | `/api/v1/torrents` | Bearer Token | 260 |
| `TNodeSpider` | TNode | `/api/torrent/advancedSearch` | CSRF Token | 108 |
| `TorrentLeech` | TorrentLeech | `/torrents/browse/list/query/{keyword}` | Cookie | 70 |
| `FireFlySpider` | FireFly | HTML 抓取 | Cookie | 120 |
| `FSMSpider` | FSM | `/api/Torrents/listTorrents` | Passkey | 110 |

### 1.4 核心问题

1. **找不找统一入口** — 每个功能模块都要写 `if 'xxx' in url`，维护成本高
2. **sites.dat 不可版本化** — Pickle 二进制，git diff 无效
3. **搜索引擎和配置捆绑** — 每种站点类型需要一个 Python 爬虫类
4. **API 站点和 HTML 站点混杂** — 搜索逻辑和站点属性合在一起

---

## 2. 设计目标

1. **统一站点定义** — 所有站点信息通过结构化 JSON 描述，存放在 `nas-tools-sites` 仓库
2. **区分 API 接口和 HTML 接口** — 定义标准化的 `site-api.schema.json` 和 `site-html.schema.json`
3. **统一特殊逻辑** — 下载链接、字幕、用户信息、连接测试全部纳入站点定义
4. **可扩展** — 新站点只需添加 JSON 配置，不需要编写 Python 代码

---

## 3. 数据模型

### 3.1 目录结构

```
nas-tools-sites/
├── schema/
│   ├── site-api.schema.json          # API 站点 JSON Schema
│   └── site-html.schema.json          # HTML 站点 JSON Schema
├── api/                               # API 站点定义（7 个）
│   ├── mteam.json                     # M-Team (x-api-key 认证)
│   ├── yemapt.json                    # YemaPT (Cookie 认证)
│   ├── rousi.json                     # Rousi (Bearer Token 认证)
│   ├── tnode.json                     # TNode (CSRF Token 认证)
│   ├── torrentleech.json              # TorrentLeech (Cookie 认证)
│   ├── fsm.json                       # FSM (Passkey 认证)
│   └── rarbg.json                     # RarBG (公共 API，Token 认证)
└── html/                              # HTML 站点定义（从 sites.dat 迁移）
    ├── hd4fans.json
    ├── hdhome.json
    └── ...
```

### 3.2 核心数据模型

```python
class SiteDefinition:
    """站点完整定义"""
    id: str                    # 唯一标识，如 "mteam"
    name: str                  # 显示名称，如 "M-Team"
    domain: str                # 主域名，如 "api.m-team.io"
    domain_aliases: List[str]  # 域名别名，如 ["kp.m-team.cc", "xp.m-team.cc"]
    encoding: str              # 页面编码，默认 "UTF-8"
    public: bool               # 是否公开站点
    language: str              # 语言过滤，如 "en"（英文站点）
    tid_pattern: str           # TID 提取正则，默认 r"\d+"，UUID 类站点用 r"[a-f0-9-]{36}"
    
    api: Optional[SiteApiConfig]           # API 站点配置
    html: Optional[SiteHtmlConfig]         # HTML 站点配置
    
    download: Optional[DownloadConfig]     # 下载链接生成规则
    subtitle: Optional[SubtitleConfig]     # 字幕下载规则
    detail_page_url: str                   # 详情页 URL 模板，如 "/detail/{tid}"


class SiteApiConfig:
    """API 站点接口配置"""
    base_url: str                          # API 基础地址
    auth: AuthConfig                       # 认证配置
    
    endpoints:
        search: EndpointConfig             # 搜索端点（必填）
        detail: EndpointConfig             # 种子详情端点（种子属性 FREE/HR/peer count）
        test_connection: EndpointConfig    # 连接测试端点
        user_info: EndpointConfig           # 用户信息端点


class AuthConfig:
    """认证配置"""
    type: str                              # api_key | bearer | cookie | csrf | passkey | token
    header_name: str                       # 请求头名称，如 "x-api-key"、"Authorization"
    token_source: str                      # 令牌来源字段（从用户 cookie/note 中读取）
    
    # CSRF 专用
    csrf_url: Optional[str]                # 获取 CSRF Token 的 URL
    csrf_selector: Optional[str]           # CSRF Token 的 HTML 选择器


class EndpointConfig:
    """API 端点配置"""
    method: str                            # GET / POST
    path: str                              # 路径模板，如 "/api/torrent/search"
    
    # 请求参数（支持 {keyword}, {page}, {tid} 等模板变量）
    params: Optional[Dict]                 # URL 查询参数（GET 时使用）
    body: Optional[Dict]                   # 请求体参数（POST 时使用）
    
    # 响应解析
    response:
        total_key: str                     # 总数路径，如 "data.total"
        items_key: str                     # 列表路径，如 "data.data"
        item_mapping: Dict                 # 字段映射表
```

### 3.3 示例：mteam.json

```json
{
  "id": "mteam",
  "name": "M-Team",
  "domain": "api.m-team.io",
  "domain_aliases": ["kp.m-team.cc", "xp.m-team.cc", "m-team.cc"],
  "encoding": "UTF-8",
  "public": false,
  "language": "en",
  "tid_pattern": "\\d+",
  "detail_page_url": "/detail/{tid}",
  "api": {
    "base_url": "https://api.m-team.io",
    "auth": {"type": "api_key", "header_name": "x-api-key"},
    "endpoints": {
      "search": {
        "method": "POST",
        "path": "/api/torrent/search",
        "body": {
          "mode": "normal",
          "keyword": "{keyword}",
          "pageNumber": "{page}",
          "pageSize": 100
        },
        "mode_mapping": {
          "MOVIE": {"mode": "movie"},
          "TV": {"mode": "tvshow"},
          "ANIME": {"mode": "normal", "categories": [405]}
        },
        "response": {
          "total_key": "data.total",
          "items_key": "data.data",
          "item_mapping": {
            "title": {"source": "name"},
            "description": {"source": "smallDescr"},
            "size": {"source": "size"},
            "seeders": {"source": "status.seeders"},
            "leechers": {"source": "status.leechers"},
            "imdbid": {"source": "imdb", "filters": [{"name": "regex", "args": ["tt\\d+", 0]}]},
            "uploadvolumefactor": {"type": "mapping", "source": "status.discount", "map": {"FREE": 1.0, "FREE_2X": 2.0, "NORMAL": 1.0}},
            "downloadvolumefactor": {"type": "mapping", "source": "status.discount", "map": {"FREE": 0.0, "FREE_2X": 0.0, "PERCENT_50": 0.5, "PERCENT_70": 0.3, "NORMAL": 1.0}},
            "labels": {"source": "status.labels", "transform": "mteam_labels"}
          }
        }
      },
      "detail": {"method": "POST", "path": "/api/torrent/detail", "body": {"id": "{tid}"}},
      "test_connection": {"method": "POST", "path": "/api/member/profile", "body": {}},
      "user_info": {"method": "POST", "path": "/api/member/profile", "body": {}}
    }
  },
  "download": {"type": "api", "method": "POST", "path": "/api/torrent/genDlToken", "body": {"id": "{tid}"}, "response_key": "data"},
  "subtitle": {
    "type": "api",
    "list": {"method": "GET", "path": "/api/subtitle/list", "params": {"torrentId": "{tid}"}, "response_key": "data"},
    "genlink": {"method": "GET", "path": "/api/subtitle/genlink", "params": {"torrentId": "{tid}", "subtitleId": "{subtitle_id}"}, "response_key": "data"},
    "download": {"method": "GET", "path": "/api/subtitle/dlV2", "params": {"torrentId": "{tid}", "subtitleId": "{subtitle_id}"}}
  }
}
```

---

## 4. 站点迁移对照表

### 4.1 API 站点（7 个）

| 站点 | 当前爬虫 | 认证 | 搜索端点 | 下载链接 | 特殊逻辑 |
|------|----------|------|----------|----------|----------|
| M-Team | `_mteam.py` 128行 | x-api-key | POST JSON | POST genDlToken | 折扣映射/标签映射 |
| YemaPT | `_yemapt.py` 115行 | Cookie | POST JSON | 获取token→拼接URL | 时区转换/标签映射 |
| Rousi | `_rousi.py` 260行 | Bearer | GET + params | 拼接域名+uuid+key | 分类ID映射/促销解析 |
| TNode | `_tnode.py` 108行 | CSRF Token | POST JSON | 拼接域名+下载路径 | CSRF提取/分类编号 |
| TorrentLeech | `_torrentleech.py` 70行 | Cookie | GET JSON | 拼接域名+fid+filename | IMDB提取 |
| FSM | `_fsm.py` 110行 | Passkey | GET + params | 拼接域名+passkey | Passkey提取/时区 |
| FireFly | `_firefly.py` 120行 | Cookie | HTML GET | HTML选择器 | HTML布局解析 |
| RarBG | `_rarbg.py` 75行 | Token | GET + params | 无(无需登录) | 第三方公开API |

### 4.2 HTML 站点（~50 个，在 sites.dat 中）

sites.dat 的 `indexer` 数组中包含 ~50 个站点的索引规则，每个站点包含：
- `search.paths` / `search.params` — 搜索 URL
- `torrents.list` / `torrents.fields` — CSS/XPath 选择器
- `category` — 类别 ID 映射
- `conf` — 促销/HR/peer count 的 XPath

这些将逐一导出为 `html/{site_id}.json`。

---

## 5. 实施路径（8 阶段）

### Phase 1: JSON Schema + Engine 扩展

**文件**：`app/sites/engine.py`

需新增的内容：

1. **加载 JSON 定义** — 当前 `definitions_dir=None`，需要实际指向 `config/sites/api/`
2. **搜索端点执行** — `resolve_search()` 统一替代 7 种专用爬虫
3. **连接测试** — `test_connection()` 替代 sites.py 的 9 处硬编码
4. **用户信息** — `resolve_user_info()` 替代 site_userinfo.py 的 5 处硬编码
5. **种子属性** — `resolve_torrent_attr()` 替代 siteconf.py 的 m-team 专用路径
6. **域名归一化** — `normalize_domain()` 替代 cookiecloud 的 m-team 子域名处理
7. **TID 去重判断** — `is_tid_based_dedup()` 替代 brush_repository.py 的 2 处硬编码

**新增字段**：

```python
class SiteDefinition:
    domain_aliases: List[str] = []    # 域名别名
    tid_pattern: str = r"\d+"          # TID 提取正则

class SiteApiConfig:
    endpoints: Dict[str, EndpointConfig]  # 扩展：search/detail/user_info/test_connection

class EndpointConfig:
    method: str           # GET / POST
    path: str             # 路径模板
    params: dict          # 查询参数
    body: dict            # 请求体
    mode_mapping: dict    # 媒体类型 → 参数映射
    response: dict        # 响应解析配置
```

### Phase 2: 7 个 API 站点 → JSON

创建文件：
- `config/sites/api/mteam.json` ✅（已创建）
- `config/sites/api/yemapt.json`
- `config/sites/api/rousi.json`
- `config/sites/api/tnode.json`
- `config/sites/api/torrentleech.json`
- `config/sites/api/fsm.json`
- `config/sites/api/firefly.json`

每个 JSON 包含完整 API 配置（搜索、详情、连接测试、用户信息、下载、字幕）。

### Phase 3: 替换爬虫分发

**文件**：`app/indexer/client/builtin.py`

当前：
```python
if   parser == "TNodeSpider":   TNodeSpider(indexer).search()
elif parser == "YemaPTSpider":  YemaPTSpider(indexer).search()
...
else:                           TorrentSpider().search()  # 通用 HTML 爬虫
```

改为：
```python
site_def = engine.get_by_url(indexer.domain)
if site_def and site_def.api:
    searcher = ApiSiteSearcher(site_def, user_config)
    return searcher.search(keyword=keyword, page=page, mtype=mtype)
else:
    TorrentSpider().search()  # 兜底：通用 HTML 爬虫
```

同时移除 `builtin.py` 中的 7 个导入。

### Phase 4: 替换 siteconf.py

**文件**：`app/sites/siteconf.py`

| 位置 | 当前 | 改为 |
|------|------|------|
| `URL_DETAIL_TEMPLATES` 字典 | 6 个站点硬编码 | engine.detail_page_url |
| `check_torrent_attr()` 中的 m-team 路径 | `if 'm-team' in url` | engine.resolve_torrent_attr() |
| `get_tid_and_url()` 中的 TID 提取 | star-space UUID / rousi UUID | engine.tid_pattern |

### Phase 5: 替换 site_subtitle.py

**文件**：`app/sites/site_subtitle.py`

```python
# 当前
if 'm-team' in page_url:
    self._download_mteam_subtitle(...)  # 整个方法

# 改为
site_def = engine.get_by_url(page_url)
if site_def and site_def.subtitle:
    self._download_subtitle_by_site_def(site_def, ...)  # 通用方法
```

删除 `_download_mteam_subtitle()` 方法（转为 JSON 驱动）。

### Phase 6: 替换 sites.py 连接测试 + user_info

**文件**：`app/sites/sites.py`、`app/sites/site_userinfo.py`

```python
# 当前（6 处硬编码）
if   'fsm' in url:    site_url += '/api/Users/infos'
elif 'yemapt' in url: site_url += '/api/user/profile'
...

# 改为
site_def = engine.get_by_url(url)
if site_def and site_def.api.test_connection:
    site_url = f"{site_def.api.base_url}{site_def.api.test_connection.path}"
```

### Phase 7: HTML sites.dat → JSON

将 `config/sites.dat` 中 `indexer` 数组逐个导出为 `html/{site_id}.json`。
同时保留 sites.dat 的 `conf` 部分（SiteConf 的 `_RSS_SITE_GRAP_CONF`）。

### Phase 8: 清理

删除文件：
- `app/indexer/client/_mteam.py`
- `app/indexer/client/_yemapt.py`
- `app/indexer/client/_rousi.py`
- `app/indexer/client/_tnode.py`
- `app/indexer/client/_torrentleech.py`
- `app/indexer/client/_firefly.py`
- `app/indexer/client/_fsm.py`
- `app/indexer/client/_rarbg.py`

删除 `app/sites/siteconf.py:URL_DETAIL_TEMPLATES`（改为 engine 动态获取）。

---

## 6. 文件变更总表

| 操作 | 文件 | 说明 |
|------|------|------|
| **新增** | `config/sites/api/*.json` | 7 个 API 站点定义 + JSON Schema |
| **新增** | `config/sites/html/*.json` | ~50 个 HTML 站点定义（Phase 7） |
| **修改** | `app/sites/engine.py` | 扩展：搜索/测试/用户信息/属性检查/域名归一 |
| **修改** | `app/sites/searchers.py` | 完善 ApiSiteSearcher（搜索模式映射、CSRF、passkey） |
| **修改** | `app/indexer/client/builtin.py` | 移除 7 种爬虫分发，改为 engine + ApiSiteSearcher |
| **修改** | `app/sites/siteconf.py` | 移除 URL_DETAIL_TEMPLATES + m-team 属性检查 |
| **修改** | `app/sites/site_subtitle.py` | 移除 `_download_mteam_subtitle`，改为 engine 驱动 |
| **修改** | `app/sites/sites.py` | 连接测试用 engine 端点替代 URL 硬编码 |
| **修改** | `app/sites/site_userinfo.py` | 用户信息用 engine 端点替代 URL 硬编码 |
| **修改** | `app/services/download_strategies.py` | 移除 4 处 `if 'm-team'` 判断 |
| **修改** | `app/db/repositories/brush_repository.py` | 去重用 engine.is_tid_based_dedup() |
| **修改** | `app/plugin_framework/.../cookiecloud/plugin.py` | 域名归一用 engine.domain_aliases |
| **修改** | `app/plugin_framework/.../autosignin/plugin.py` | M-Team 签到用 engine 端点 |
| **删除** | `app/indexer/client/_mteam.py` 等 8 个 | 改为 JSON 驱动 |

---

## 7. 站点属性管理（用户配置）

需要单独存储的用户配置字段（不放在站点 JSON 定义中）：

| 字段 | 说明 | 存储位置 |
|------|------|----------|
| `cookie` | 认证 Cookie/API Key | 数据库 CONFIG_SITE |
| `headers` | 自定义 HTTP 头 | 数据库 NOTE JSON |
| `ua` | User-Agent | 数据库 NOTE JSON |
| `proxy` | 是否启用代理 | 数据库 NOTE JSON |
| `chrome` | 是否使用浏览器渲染 | 数据库 NOTE JSON |
| `pri` | 优先级 | 数据库 CONFIG_SITE |
| `rssurl` | RSS 链接 | 数据库 CONFIG_SITE |
| `signurl` | 站点 URL（匹配站点定义） | 数据库 CONFIG_SITE |
| `rule` | 过滤规则组 ID | 数据库 NOTE JSON |
| `INCLUDE` | 功能开关（D=订阅, S=刷流, T=统计） | 数据库 CONFIG_SITE |

---

## 8. 认证方式对照

| auth.type | 说明 | 令牌来源 | 示例站点 |
|-----------|------|----------|----------|
| `api_key` | API Key 请求头 | 用户 cookie 字段 | M-Team (x-api-key) |
| `bearer` | Bearer Token | 用户 cookie 字段 | Rousi (Authorization: Bearer) |
| `cookie` | Cookie 认证 | 用户 cookie 字段 | YemaPT、TorrentLeech |
| `csrf` | CSRF Token | 从页面动态提取 | TNode |
| `passkey` | Passkey | 从用户信息 API 获取 | FSM |
| `token` | 公开 API Token | 从 API 获取 | RarBG |
