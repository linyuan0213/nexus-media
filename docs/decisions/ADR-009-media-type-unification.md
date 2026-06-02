# ADR-009: 媒体类型命名统一重构方案

## Status

Accepted / Implemented

## Date

2026-05-31（决策）/ 2026-06-01（实施完成）

## Context

系统中存在电影、电视剧、动漫三种媒体类型，但在枚举值、字符串表示、数据库存储、API 返回、前端展示等层面使用了多种不同的命名，导致维护困难和潜在 bug。

### 重构前命名混乱现状

#### 1. 枚举层

```python
# app/utils/types.py
class MediaType(Enum):
    MOVIE = "电影"      # 枚举名 MOVIE，值是中文
    TV = "剧集"         # 枚举名 TV，值是中文
    ANIME = "动漫"      # 枚举名 ANIME，值是中文
    UNKNOWN = "未知"
```

问题：枚举值是中文字符串，序列化到 JSON/数据库时不稳定。

#### 2. 字符串层（至少 6 种表示）

| 含义 | 枚举名 | 枚举值 | 数据库 | API 返回 | 站点 cat | 缩写 |
|------|--------|--------|--------|----------|----------|------|
| 电影 | `MOVIE` | `"电影"` | `"电影"` / `"MOV"` | `"MOV"` / `"movie"` | `"MOVIE"` | `"mo"` |
| 电视剧 | `TV` | `"剧集"` | `"剧集"` / `"TV"` | `"TV"` / `"tv"` | `"TV"` | `"tv"` |
| 动漫 | `ANIME` | `"动漫"` | `"动漫"` / `"ANI"` | `"ANI"` / `"anime"` | `"ANIME"` | `"an"` |

#### 3. 代码中混用示例

```python
# 1. 数据库查询映射 — 枚举值是中文
if media_item.type == MediaType.TV:
    mtype = "TV"
elif media_item.type == MediaType.MOVIE:
    mtype = "MOVIE"
else:
    mtype = "ANI"

# 2. API 返回 — 枚举值直接返回中文
return {"type": media_info.type.value}  # 返回 "电影" / "剧集" / "动漫"

# 3. 站点分类映射 — 枚举名转站点代码
cat_map = {"MOVIE": "mo", "TV": "tv", "ANIME": "an"}

# 4. TMDB 查询 — 枚举转字符串（ANIME 被忽略）
typestr = "MOV" if mtype == MediaType.MOVIE else "TV"
# 注意：这里没有 ANIME 分支，动漫被当成 TV 处理

# 5. 条件判断 — 枚举比较（正确用法，但值是中文）
getattr(x, "type", None) in (MediaType.TV, MediaType.ANIME)

# 6. 数据库存储 — TYPE 字段存中文
TYPE = Column(String(20))  # 存 "电影", "剧集", "动漫"
```

#### 4. 具体问题

| 问题 | 位置 | 影响 |
|------|------|------|
| 枚举值是中文 | `MediaType` | JSON 序列化后无法反序列化（中文字段名问题） |
| 数据库 TYPE 存中文 | 多张表 | 查询时需要字符串匹配，易出错；国际化困难 |
| API 返回不统一 | `subscription.py`, `search.py` | 前端需要处理 `"MOV"`, `"TV"`, `"ANI"`, `"movie"`, `"tv"` 等多种格式 |
| 动漫类型被忽略 | `tmdb_lookup.py:575` | `typestr = "MOV" if mtype == MediaType.MOVIE else "TV"` — ANIME 被当成 TV |
| 缩写不一致 | `search_repository.py` | TV 用 `"TV"`, 电影用 `"MOVIE"`, 动漫用 `"ANI"` |
| 站点映射硬编码 | `html_searcher.py` | 每个站点可能有自己的 cat 编码，目前集中在代码里 |

---

## 目标

1. **单一事实来源**：所有媒体类型通过 `MediaType` 枚举表示，消除字符串硬编码
2. **序列化统一**：数据库、API、缓存中的媒体类型使用统一的小写英文格式
3. **前端展示隔离**：中文名称（`电影`/`电视剧`/`动漫`）仅在前端本地化层使用
4. **消除隐式转换**：禁止在代码中手写 `"MOV"` / `"TV"` / `"ANI"` 等字符串判断
5. **动漫类型正确处理**：TMDB 查询等场景不再把 ANIME 隐式当成 TV

---

## 方案设计

### 新枚举定义

```python
# app/utils/types.py

class MediaType(Enum):
    """媒体类型枚举

    - name: 大写英文（代码中使用，如 MediaType.MOVIE）
    - value: 小写英文（序列化/数据库存储/API 返回）
    - display: 中文名称（仅前端展示，通过 display_name() 获取）
    """
    MOVIE = "movie"
    TV = "tv"
    ANIME = "anime"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        """获取前端展示名称"""
        return _MEDIA_TYPE_DISPLAY_NAMES.get(self, "未知")

    @classmethod
    def from_string(cls, value: str) -> "MediaType":
        """从字符串反序列化，统一归一化为小写英文"""
        normalized = str(value).strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.UNKNOWN

    def __str__(self) -> str:
        """默认字符串表示为小写英文 value"""
        return self.value


# 中文展示名称映射（仅用于前端/日志）
_MEDIA_TYPE_DISPLAY_NAMES: dict[MediaType, str] = {
    MediaType.MOVIE: "电影",
    MediaType.TV: "电视剧",
    MediaType.ANIME: "动漫",
    MediaType.UNKNOWN: "未知",
}
```

### 统一规则

| 层级 | 重构前 | 重构后 |
|------|--------|--------|
| **枚举名** | `MediaType.MOVIE` | `MediaType.MOVIE`（不变） |
| **枚举值** | `"电影"` / `"剧集"` / `"动漫"` | `"movie"` / `"tv"` / `"anime"` |
| **数据库存储** | `"电影"` / `"剧集"` / `"ANI"` 等 | `"movie"` / `"tv"` / `"anime"` |
| **API 返回** | `"MOV"` / `"TV"` / `"ANI"` | `"movie"` / `"tv"` / `"anime"` |
| **前端展示** | 直接使用 API 返回值 | 通过 `MediaType.display_name` 映射为中文 |
| **日志输出** | 混用 | 统一使用 `media_type.value`（小写英文） |

### 核心工具方法

```python
# app/utils/media_type_utils.py

class MediaTypeMapper:
    """媒体类型映射器 — 统一管理类型转换"""

    # TMDB 类型映射
    TMDB_MAP: dict[str, MediaType] = {
        "movie": MediaType.MOVIE,
        "tv": MediaType.TV,
    }

    # 站点 cat 映射（按站点可配置）
    SITE_CAT_MAP: dict[str, dict[str, MediaType]] = {
        "default": {
            "movie": MediaType.MOVIE,
            "tv": MediaType.TV,
            "anime": MediaType.ANIME,
        },
        # 可按站点扩展
    }

    @classmethod
    def from_tmdb(cls, tmdb_type: str) -> MediaType:
        """从 TMDB 类型字符串转枚举"""
        return cls.TMDB_MAP.get(tmdb_type.lower(), MediaType.UNKNOWN)

    @classmethod
    def to_tmdb(cls, media_type: MediaType) -> str:
        """从枚举转 TMDB 类型字符串"""
        if media_type == MediaType.MOVIE:
            return "movie"
        if media_type in (MediaType.TV, MediaType.ANIME):
            return "tv"
        return ""

    @classmethod
    def from_site_cat(cls, cat: str, site: str = "default") -> MediaType:
        """从站点分类编码转枚举"""
        site_map = cls.SITE_CAT_MAP.get(site, cls.SITE_CAT_MAP["default"])
        return site_map.get(cat.lower(), MediaType.UNKNOWN)

    @classmethod
    def to_site_cat(cls, media_type: MediaType, site: str = "default") -> str:
        """从枚举转站点分类编码"""
        site_map = cls.SITE_CAT_MAP.get(site, cls.SITE_CAT_MAP["default"])
        # 反向查找
        for cat, mt in site_map.items():
            if mt == media_type:
                return cat
        return ""
```

### 代码改造示例

**重构前**：
```python
# 1. 数据库查询 — 手动字符串映射
if media_item.type == MediaType.TV:
    mtype = "TV"
elif media_item.type == MediaType.MOVIE:
    mtype = "MOVIE"
else:
    mtype = "ANI"

# 2. API 返回 — 中文转缩写
"type": "MOV" if str(item.TYPE or "") == "电影" else "TV"

# 3. TMDB 查询 — 枚举转字符串（ANIME 被忽略）
typestr = "MOV" if mtype == MediaType.MOVIE else "TV"

# 4. 条件判断 — 硬编码字符串
if media_info.type != "电影" and media_info.get_episode_list():
    ...
```

**重构后**：
```python
# 1. 数据库查询 — 直接用枚举值
mtype = media_item.type.value  # "movie" / "tv" / "anime"

# 2. API 返回 — 直接用枚举值
"type": item.TYPE.value  # "movie" / "tv" / "anime"

# 3. TMDB 查询 — 使用映射器
typestr = MediaTypeMapper.to_tmdb(mtype)  # "movie" / "tv"

# 4. 条件判断 — 用枚举比较
if media_info.type != MediaType.MOVIE and media_info.get_episode_list():
    ...
```

---

## 实施记录

### Phase 1：重构枚举和工具（已完成）

- **修改 `app/utils/types.py`**：`MediaType` 枚举值改为小写英文；添加 `display_name` property、`from_string()` 类方法、`__str__()` 返回 `self.value`；删除 `MovieTypes` / `TvTypes`
- **新建 `app/utils/media_type_utils.py`**：`MediaTypeMapper` 类，TMDB / 站点 cat 映射

### Phase 2：数据库迁移（已完成）

- **Alembic 迁移脚本**：`1fd6712c2b1f_unify_media_type_to_lowercase.py`
  - 更新 7 张表的媒体类型字段：`DOWNLOAD_HISTORY`, `SUBSCRIBE_HISTORY`, `SUBSCRIBE_TORRENTS`, `SEARCH_RESULT_INFO`, `TRANSFER_HISTORY`, `TMDB_BLACKLIST`, `MEDIASYNC_ITEMS`
  - 映射规则：`电影`/`MOVIE`/`MOV` → `movie`，`剧集`/`电视剧`/`TV` → `tv`，`动漫`/`ANIME`/`ANI` → `anime`

### Phase 3：代码层改造（已完成）

涉及约 40+ 文件：

| 层级 | 修改文件 |
|------|----------|
| API Routers | `subscription.py`, `media.py`, `words.py`, `sync.py` |
| Services | `media_info_service.py`, `sync_service.py`, `search_result_service.py`, `search_message_service.py`, `tmdb_blacklist_service.py`, `transfer/filetransfer_service.py`, `rss_automation/executor.py`, `transfer_history_service.py`, `media_file_service.py`, `system/info.py`, `media_recommendation_service.py`, `search_web_service.py` |
| Subscribe | `monitor.py`, `finish_service.py`, `history_service.py`, `rss_feed.py`, `base_search.py`, `refresh_service.py`, `add_service.py`, `update_service.py`, `query_service.py`, `matcher.py`, `search_engine.py` |
| Media/Lookup | `tmdb_lookup.py`, `tmdb_discover.py`, `html_searcher.py`, `bangumi.py`, `douban.py` |
| Mediaserver | `plex.py`, `emby.py`, `jellyfin.py`, `fnos.py`, `media_server.py` |
| Repository/Domain | `search_repository.py`, `media_repository.py`, `download.py`, `word.py` |
| Message/Plugins | `message_builder.py`, `doubanrank/plugin.py`, `doubansync/plugin.py` |
| Agent | `tool_executor.py` |

### Phase 4：前端适配（待前端仓库实施）

- 前端接收 `movie` / `tv` / `anime`，通过映射表转为中文展示
- 删除前端所有硬编码 `"MOV"` / `"TV"` / `"ANI"` 判断
- `zh-CN/page.json` 中添加 `media_type` 映射：
  ```json
  {
    "media_type": {
      "movie": "电影",
      "tv": "电视剧",
      "anime": "动漫",
      "unknown": "未知"
    }
  }
  ```

---

## 决策

按本方案四阶段全部实施。

---

## Consequences

### 正面影响

- **单一事实来源**：`MediaType` 枚举是唯一的类型定义，消除字符串硬编码
- **序列化稳定**：枚举值为小写英文，JSON/API/数据库通用
- **国际化友好**：中文展示名称集中在前端本地化文件，支持多语言切换
- **类型安全**：IDE 自动补全和类型检查生效，减少 typo
- **ANIME 类型不再被隐式当成 TV**：`MediaTypeMapper.to_tmdb()` 正确处理动漫类型

### 负面影响

- **数据库迁移**：需要更新所有 TYPE 字段，大表可能有性能影响
- **前端适配**：前端需同步更新类型映射
- **外部接口影响**：站点 cat 映射变更可能影响已有站点的搜索/刷流

### 验证检查清单

实施后运行以下检查确保无遗漏：

```bash
# 1. 检查代码中是否还有非标准格式字符串
grep -r '"电影"\|"剧集"\|"动漫"\|"MOV"\|"ANI"\|"movie"\|"tv"\|"anime"' src/ --include="*.py" | grep -v "display_name"

# 2. 检查数据库 TYPE 字段是否统一
# SQL: SELECT DISTINCT type FROM subscribe_movies UNION SELECT DISTINCT type FROM subscribe_tvs;

# 3. 检查 API 返回是否统一
# curl /api/media/list | jq '.data[].type' | sort | uniq
```

### 质量检查结果

- `ruff check src/ tests/` — 通过
- `pyright src/ tests/` — 0 errors
- `pytest tests/ -v` — 621 passed, 0 failed
