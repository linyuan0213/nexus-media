# 媒体模块精简架构设计

## 1. 问题

旧 `Media` 类被 25+ 个文件引用，每个文件都创建自己的实例。
大量调用是**已知 tmdb_id 查详情**或**查数据库获取已识别记录**，这些不需要经过"文件名识别"流程。

## 2. 设计原则

- **识别和查询分离**：`MediaService` 只做"文件名 → 媒体信息"识别
- **已知 id 直接查缓存**：`MediaCache` 提供 `get_tmdb_info(mtype, tmdbid)`
- **优先查数据库**：`MediaInfoRepository` 从下载记录/订阅记录中拿 tmdb_id
- **MediaService 不要到处都是**

## 3. 架构

```
app/media/
├── service.py              # MediaService — 仅做文件名识别
├── repository.py           # MediaInfoRepository — 查数据库
├── cache/
│   └── media_cache.py      # MediaCache — 查 TMDB 缓存
├── lookup/
│   ├── base.py             # BaseLookup
│   └── tmdb_lookup.py      # TmdbLookup — TMDB API 封装
└── models.py               # MediaInfo — pydantic 模型
```

### 3.1 MediaService — 仅识别

```python
class MediaService:
    """只做文件名识别"""

    def identify(self, title, subtitle="", mtype=None) -> Optional[MediaInfo]:
        """从文件名识别媒体信息（Parser + Lookup）"""
        ...

    def identify_files(self, file_list, ...) -> dict[str, MediaInfo]:
        """批量文件识别"""
        ...
```

**使用场景**：
- RSS 新条目识别
- 索引器搜索结果识别
- 手动搜索时用户输入识别
- 文件扫描（无下载记录时）

### 3.2 MediaCache — 查 TMDB 详情

```python
class MediaCache:
    """查 TMDB 缓存 — 已知 tmdb_id"""

    def get_tmdb_info(self, mtype, tmdbid, language=None) -> Optional[dict]:
        """从缓存或 API 获取 TMDB 详情"""
        ...
```

**使用场景**：
- 已有 tmdb_id，需要补充 genres、overview、poster 等
- 订阅详情页展示
- 下载历史详情展示
- 同步服务检查文件

### 3.3 MediaInfoRepository — 查数据库

```python
class MediaInfoRepository:
    """从数据库查已识别的媒体记录"""

    def get_by_download_path(self, path: str) -> Optional[MediaRecord]:
        """根据下载路径查下载历史，返回 tmdb_id + type"""
        ...

    def get_by_torrent_name(self, name: str) -> Optional[MediaRecord]:
        """根据种子名查下载历史"""
        ...
```

**使用场景**：
- 文件转移时先查下载记录
- 下载服务中根据种子名查历史
- 重处理时查原始记录

## 4. 调用模式对比

### 4.1 下载服务（下载搜索结果）

**旧代码**：
```python
media = self._media.get_media_info(title=res.TORRENT_NAME, subtitle=res.DESCRIPTION)
```

**新代码**：
```python
# 先查数据库（下载历史）
record = self._media_repo.get_by_torrent_name(res.TORRENT_NAME)
if record and record.tmdbid:
    info = self._media_cache.get_tmdb_info(record.type, record.tmdbid)
    media = MediaInfo.from_tmdb_info(info)
else:
    # 数据库没有，再走识别
    media = self._media_service.identify(res.TORRENT_NAME, res.DESCRIPTION)
```

### 4.2 文件转移服务

**旧代码**：
```python
Medias = self.media.get_media_info_on_files(file_list, tmdb_info, media_type, ...)
```

**新代码**：
```python
# 已保留：_lookup_download_record 查数据库获取 tmdb_info
tmdb_info, media_type = self._lookup_download_record(in_path)

# 如果数据库有记录，直接用 tmdb_info，不走识别
if tmdb_info:
    Medias = self._build_media_from_tmdb(file_list, tmdb_info, media_type)
else:
    # 数据库没有，才走识别
    Medias = self._media_service.identify_files(file_list)
```

### 4.3 订阅搜索

**旧代码**：
```python
tmdb_info = self._media.get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
media_info = self._media.get_media_info(title="%s %s" % (name, year), mtype=mtype, strict=True)
```

**新代码**：
```python
# 订阅项本身已有 tmdb_id，直接查缓存
tmdb_info = self._media_cache.get_tmdb_info(mtype, tmdbid)
media_info = MediaInfo.from_tmdb_info(tmdb_info)
```

### 4.4 同步服务

**旧代码**：
```python
tmdb_info = self._media.get_tmdb_info(mtype=media_type, tmdbid=tmdbid)
```

**新代码**：
```python
# 直接从缓存查
tmdb_info = self._media_cache.get_tmdb_info(media_type, tmdbid)
```

### 4.5 RSS 核心

**旧代码**：
```python
return idx, self.media.get_media_info(title=title)
```

**新代码**：
```python
# RSS 只有标题，必须识别
return idx, self._media_service.identify(title=title)
```

### 4.6 索引器批量识别

**旧代码**：
```python
return name, self.media.get_media_info(title=name, subtitle=desc)
```

**新代码**：
```python
# 索引器只有文件名，必须识别
return name, self._media_service.identify(title=name, subtitle=desc)
```

## 5. 文件改造清单

| 文件 | 当前用法 | 建议改造 |
|------|---------|---------|
| `download_service.py` | `get_media_info(title)` | 先查 `MediaInfoRepository`，没有再 `identify()` |
| `filetransfer_service.py` | `get_media_info_on_files()` + `get_tmdb_info()` | 已有 `_lookup_download_record`，保留；`get_tmdb_info` 改为 `MediaCache` |
| `rss_core.py` | `get_media_info(title)` | 保留 `MediaService.identify()` |
| `rss_service.py` | `get_media_info()` + `get_tmdb_info()` | `get_tmdb_info` 改为 `MediaCache` |
| `subscribe_service.py` | `get_media_info()` + `get_tmdb_info()` | 订阅已有 tmdb_id，用 `MediaCache` |
| `subscribe_search_engine.py` | `get_media_info()` + `get_tmdb_info()` | 用 `MediaCache` |
| `sync_service.py` | `get_tmdb_info()` | 用 `MediaCache` |
| `tmdb_blacklist_service.py` | `get_tmdb_info()` | 用 `MediaCache` |
| `media_info_service.py` | `get_media_info()` + `get_tmdb_info()` | 混合：识别用 `MediaService`，查详情用 `MediaCache` |
| `words_service.py` | `get_tmdb_info()` | 用 `MediaCache` |
| `media_file_service.py` | `get_media_info()` + `get_tmdb_info()` | 先查数据库，再 `MediaCache` |
| `web_utils.py` | `get_media_info()` + `get_tmdb_info()` | 改为 `MediaCache` + `MediaService` |
| `wallpaper.py` | `get_random_discover_backdrop()` | 保留 `MediaService`（发现类方法） |
| `mediasyncdel/plugin.py` | `get_episode_images()` + `get_tmdb_backdrop()` | 保留 `MediaService` 或直接用 `TmdbLookup` |
| `search_torrents.py` | 多处 `Media()` | 按需：有 tmdb_id 用 `MediaCache`，无则 `identify()` |
| `search_service.py` | `get_tmdb_en_title()` + `get_tmdb_zhtw_title()` | 保留 `MediaService` 或移入 `MediaCache` |
| `result_filter.py` | `merge_media_info()` | 工具方法，可独立为函数 |
| `batch_identifier.py` | `get_media_info()` | 保留 `MediaService.identify()` |
| `brush_rule_engine.py` | `get_media_info()` | 保留 `MediaService.identify()` |
| `doubanrank/plugin.py` | `get_media_info()` | 保留 `MediaService.identify()` |
| `media_recommendation_service.py` | `get_tmdb_hot_*()` | 保留 `MediaService`（发现类方法） |
| `media_server.py` | 持有 Media 实例 | 移除（未直接使用） |
| `warmer.py` | `get_tmdb_trending_all_week()` | 保留 `MediaService` |
| `scraper.py` | 已改为 `MediaService` | 验证是否需要收窄 |

## 6. 收口设计

**不要在 25 个文件里各创建实例**。

```python
# app/media/__init__.py

_media_service = None
_media_cache = None

def get_media_service() -> MediaService:
    global _media_service
    if _media_service is None:
        _media_service = MediaService()
    return _media_service

def get_media_cache() -> MediaCache:
    global _media_cache
    if _media_cache is None:
        _media_cache = MediaCache()
    return _media_cache
```

**服务类构造函数**：
```python
class DownloadService:
    def __init__(self, media_service=None, media_cache=None, media_repo=None):
        self._media_service = media_service or get_media_service()
        self._media_cache = media_cache or get_media_cache()
        self._media_repo = media_repo or MediaInfoRepository()
```

**工具函数**：
```python
def some_utility(tmdbid):
    # 不需要 MediaService，直接查缓存
    return get_media_cache().get_tmdb_info(MediaType.MOVIE, tmdbid)
```

## 7. 实施优先级

1. **Phase 1**: 补齐 `MediaCache`（已存在，添加 `get_tmdb_info` 方法）
2. **Phase 2**: 创建 `MediaInfoRepository`
3. **Phase 3**: 修改 `download_service.py`、`filetransfer_service.py`（先查数据库模式）
4. **Phase 4**: 修改纯 `get_tmdb_info()` 调用方（`sync_service`, `words_service`, `tmdb_blacklist_service`, `subscribe_service`）
5. **Phase 5**: 修改混合调用方（`media_info_service`, `rss_service`, `search_torrents`）
6. **Phase 6**: 清理未使用的 `MediaService` 实例
