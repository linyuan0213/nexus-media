# 媒体识别模块重构设计文档

## 1. 现状分析

### 1.1 代码规模

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/media/media.py` | 2480 | TMDB API、搜索、AI fallback、缓存、人员查询、图像、分类... |
| `app/media/meta/_base.py` | 714 | MetaBase 基类（模型+方法混合） |
| `app/media/meta/metaanime.py` | 225 | anitopy 动漫解析 |
| `app/media/meta/metavideo.py` | 559 | Token 正则影视解析 |
| `app/media/meta/metainfo.py` | 63 | MetaInfo() 工厂函数 |
| `app/media/meta/_model.py` | 124 | Pydantic 数据模型 |
| `app/indexer/core/batch_identifier.py` | 65 | 索引器批量识别（ThreadPool） |
| `app/services/rss_core.py` | 458 | RSS 批量识别（ThreadPool） |

### 1.2 核心问题

#### 问题1：Media 类职责过重

`Media` 类同时承担：
- TMDB API 客户端（`search.movies`/`tv_shows`/`multi`）
- 搜索策略（按年份、按季、模糊匹配、精确匹配）
- AI fallback 识别（`__search_ai`）
- WEB 抓取 fallback（`__search_tmdb_web`）
- 搜索引擎 fallback（`__search_engine`）
- 缓存管理（`redis_cache`、`TMDBCache`）
- 图像代理（`ImageProxyHelper`）
- 人员查询（`search_tmdb_person`）
- 名称匹配（`__compare_tmdb_names`）
- 中文标题转换（`__update_tmdbinfo_cn_title`）

#### 问题2：识别链路不清晰

`get_media_info()` 的 fallback 链长达 7 层：

```
MetaInfo(title) ──→ 本地正则解析（MetaAnime/MetaVideo）
    │
    ▼
TMDB 搜索（按类型+年份）
    │
    ├─ 失败 → 去掉年份再查
    ├─ 失败 → 多类型查询（movie + tv）
    ├─ 失败 → WEB 抓取（themoviedb.org）
    ├─ 失败 → AI 识别（MediaRecognizer）
    └─ 失败 → 搜索引擎关键词猜测
    │
    ▼
补充 TMDB 详情（genres/中文标题）
    │
    ▼
写入 Redis 缓存
```

问题：
- 每层 fallback 都增加延迟，但 caller 无感知
- AI 放在倒数第二，优先度低
- 没有早期退出机制（比如 MetaInfo 已明确是 anime，仍先查 movie）

#### 问题3：批量识别重复实现

| 场景 | 文件 | 实现 | 问题 |
|------|------|------|------|
| RSS | `rss_core.py:193` | `ThreadPoolExecutor(4)` + `get_media_info()` | 与索引器不共享逻辑 |
| 索引器 | `batch_identifier.py:62` | `ThreadPoolExecutor(4)` + `get_media_info()` | 与 RSS 不共享逻辑 |
| AI batch | `media.py:88` | `recognize_batch()`（当前有 bug） | 未被任何批量场景调用 |

#### 问题4：MetaInfo 与 MetaBase 职责模糊

- `MetaInfo()` 返回 `MetaBase` 子类实例
- `MetaBase` 既是数据模型（继承 `MediaInfoModel`）又是行为类（`get_season_string()` 等 100+ 方法）
- `MediaInfoModel` 定义了字段，但 `MetaBase` 又动态添加字段（`set_torrent_info`）

#### 问题5：Parser 与 Lookup 耦合

`Media.get_media_info()` 把「文件名解析」和「TMDB 查询」绑在一起：
- 调用者只想解析文件名，也被迫走 TMDB
- 调用者只想查 TMDB，也必须先 `MetaInfo()`
- 批量场景无法先做统一解析再统一查询

---

## 2. 目标

1. **解耦 Parser 与 Lookup**：文件名解析和外部数据库查询分离
2. **统一批量入口**：RSS、索引器、文件扫描共用一套批量处理逻辑
3. **清晰 fallback 链**：每层有明确优先级和超时控制
4. **Media 类拆分**：按职责拆分为独立模块
5. **LLM 深度集成**：Agent 作为首选解析器，而非 fallback

---

## 3. 重构后架构

```
┌─────────────────────────────────────────────────────────────┐
│                      MediaService (Facade)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Parser    │  │   Lookup    │  │   BatchProcessor    │  │
│  │   Layer     │  │   Layer     │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘  │
│         │                │                                   │
│  ┌──────┴────────────────┴─────────────────────────────┐    │
│  │                   Cache Layer                        │    │
│  │  (Redis TMDB info / Memory media ident / Season map) │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 目录结构

```
app/media/
├── __init__.py                    # 导出 MediaService, MediaInfo
├── models.py                      # MediaInfo (pydantic, 纯数据)
├── parser/
│   ├── __init__.py
│   ├── base.py                    # ParserResult, BaseParser
│   ├── regex.py                   # RegexParser (MetaAnime + MetaVideo 合并)
│   ├── anitopy_adapter.py         # anitopy 包装
│   ├── token_adapter.py           # Tokens 包装
│   └── llm.py                     # LLMParser (MediaRecognizer 包装)
├── lookup/
│   ├── __init__.py
│   ├── base.py                    # LookupResult, BaseLookup
│   ├── tmdb.py                    # TmdbLookup
│   ├── douban.py                  # DoubanLookup
│   └── bangumi.py                 # BangumiLookup
├── batch/
│   ├── __init__.py
│   └── processor.py               # BatchProcessor
├── cache/
│   ├── __init__.py
│   └── media_cache.py             # 媒体识别结果缓存
└── service.py                     # MediaService (facade)
```

---

## 4. 核心设计

### 4.1 Parser 层

**Parser 只做一件事：从文件名提取结构化信息。**

```python
# app/media/parser/base.py
from pydantic import BaseModel
from typing import Optional
from app.utils.types import MediaType


class ParserResult(BaseModel):
    """文件名解析结果 — 纯数据，无外部依赖"""
    title_en: Optional[str] = None
    title_cn: Optional[str] = None
    year: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    resource_pix: Optional[str] = None
    video_encode: Optional[str] = None
    audio_encode: Optional[str] = None
    resource_team: Optional[str] = None
    type: Optional[MediaType] = None
    confidence: float = 0.0           # 解析置信度


class BaseParser:
    """解析器基类"""

    def parse(self, title: str, subtitle: str = "") -> Optional[ParserResult]:
        raise NotImplementedError

    def parse_batch(self, titles: list[str]) -> list[Optional[ParserResult]]:
        """默认逐条解析，子类可 override 实现 true batch"""
        return [self.parse(t) for t in titles]
```

**RegexParser（合并 MetaAnime + MetaVideo）**：

```python
# app/media/parser/regex.py
class RegexParser(BaseParser):
    """基于正则的本地解析器 — 合并 MetaAnime 和 MetaVideo"""

    def parse(self, title: str, subtitle: str = "") -> Optional[ParserResult]:
        # 1. 判断 anime（【】/[] 模式）
        if self._is_anime(title):
            return self._parse_anime(title, subtitle)
        # 2. 走 video 解析（Tokens）
        return self._parse_video(title, subtitle)
```

**LLMParser（包装 MediaRecognizer）**：

```python
# app/media/parser/llm.py
class LLMParser(BaseParser):
    """基于 LLM 的解析器"""

    def __init__(self, provider_name: str = ""):
        self._recognizer = MediaRecognizer(provider_name)

    @property
    def ready(self) -> bool:
        return self._recognizer.ready

    def parse(self, title: str, subtitle: str = "") -> Optional[ParserResult]:
        result = self._recognizer.recognize(title)
        if not result:
            return None
        return ParserResult(
            title_en=result.title_en,
            title_cn=result.title_cn,
            year=str(result.year) if result.year else None,
            season=result.season,
            episode=result.episode,
            resource_pix=result.resolution,
            video_encode=result.video_codec,
            audio_encode=result.audio_codec,
            resource_team=result.release_group,
            type=self._map_type(result.type),
            confidence=0.9,
        )

    def parse_batch(self, titles: list[str]) -> list[Optional[ParserResult]]:
        results = self._recognizer.recognize_batch(titles)
        return [self._convert(r) for r in results]
```

### 4.2 Lookup 层

**Lookup 只做一件事：根据解析结果查询外部数据库。**

```python
# app/media/lookup/base.py
class LookupResult(BaseModel):
    tmdb_id: Union[int, str] = 0
    title: Optional[str] = None
    original_title: Optional[str] = None
    media_type: Optional[MediaType] = None
    year: Optional[str] = None
    # ... TMDB 完整字段


class BaseLookup:
    def lookup(self, parsed: ParserResult, hint_type: MediaType = None) -> Optional[LookupResult]:
        raise NotImplementedError
```

**TmdbLookup（从 Media 类拆分）**：

```python
# app/media/lookup/tmdb.py
class TmdbLookup(BaseLookup):
    """TMDB 查询 — 封装所有 TMDB 搜索策略"""

    def lookup(self, parsed: ParserResult, hint_type: MediaType = None) -> Optional[LookupResult]:
        # 策略1: 按类型+年份精确搜索
        # 策略2: 去掉年份再查
        # 策略3: 多类型查询
        # 策略4: WEB 抓取（可选）
        pass
```

### 4.3 统一的 MediaInfo 模型

```python
# app/media/models.py
class MediaInfo(BaseModel):
    """统一的媒体信息模型 — 替代 MetaBase + MediaInfoModel"""
    model_config = {"extra": "allow"}

    # --- 解析结果（来自 Parser） ---
    org_string: Optional[str] = None
    type: Optional[MediaType] = None
    cn_name: Optional[str] = None
    en_name: Optional[str] = None
    year: Optional[str] = None
    begin_season: Optional[int] = None
    end_season: Optional[int] = None
    begin_episode: Optional[int] = None
    end_episode: Optional[int] = None
    resource_pix: Optional[str] = None
    video_encode: Optional[str] = None
    audio_encode: Optional[str] = None
    resource_team: Optional[str] = None

    # --- 查询结果（来自 Lookup） ---
    tmdb_id: Union[int, str] = 0
    tmdb_info: dict = Field(default_factory=dict)

    # --- 种子附加信息 ---
    site: Optional[str] = None
    enclosure: Optional[str] = None
    size: int = 0
    seeders: int = 0

    # --- 便捷方法（纯计算，无外部依赖） ---
    def get_name(self) -> str: ...
    def get_season_string(self) -> str: ...
    def get_episode_string(self) -> str: ...
    def get_title_string(self) -> str: ...
```

### 4.4 BatchProcessor

```python
# app/media/batch/processor.py
class BatchProcessor:
    """统一批量处理入口 — RSS、索引器、文件扫描共用"""

    def __init__(self, parser: BaseParser, lookup: BaseLookup, cache: MediaCache):
        self.parser = parser
        self.lookup = lookup
        self.cache = cache

    def process(
        self,
        items: list[dict],           # [{"title": "...", "subtitle": "...", ...}]
        enable_lookup: bool = True,   # 是否查询 TMDB
        enable_cache: bool = True,
    ) -> list[Optional[MediaInfo]]:
        """
        批量处理流程：
        1. 批量解析所有 title（优先 LLM batch）
        2. 去重后批量查询 TMDB
        3. 组装 MediaInfo
        """
        titles = [i["title"] for i in items]

        # 阶段1: 批量解析
        parsed_list = self.parser.parse_batch(titles)

        # 阶段2: 批量查询（去重）
        if enable_lookup:
            unique_keys = {}
            for idx, parsed in enumerate(parsed_list):
                if not parsed:
                    continue
                key = f"{parsed.title_en or parsed.title_cn}:{parsed.year}:{parsed.type}"
                if key not in unique_keys:
                    unique_keys[key] = []
                unique_keys[key].append(idx)

            # 并发查询去重后的条目
            lookup_results = {}
            # ... ThreadPoolExecutor or sequential ...

        # 阶段3: 组装
        results = []
        for idx, item in enumerate(items):
            parsed = parsed_list[idx]
            info = MediaInfo.from_parser(parsed)
            # 附加种子信息
            info.enclosure = item.get("enclosure")
            info.size = item.get("size", 0)
            results.append(info)

        return results
```

### 4.5 MediaService（Facade）

```python
# app/media/service.py
class MediaService:
    """媒体识别服务门面 — 对外统一接口"""

    def __init__(self):
        self.parser = self._build_parser()
        self.lookup = TmdbLookup()
        self.cache = MediaCache()
        self.batch = BatchProcessor(self.parser, self.lookup, self.cache)

    def _build_parser(self) -> BaseParser:
        """根据配置选择解析器"""
        cfg = Config().get_config("agent") or {}
        if cfg.get("enabled") and cfg.get("media_recognizer_enabled"):
            llm = LLMParser()
            if llm.ready:
                return llm
        return RegexParser()

    def identify(self, title: str, subtitle: str = "", mtype: MediaType = None) -> Optional[MediaInfo]:
        """单条识别 — 替代 Media.get_media_info()"""
        # 1. 解析
        parsed = self.parser.parse(title, subtitle)
        if not parsed:
            return None

        info = MediaInfo.from_parser(parsed)

        # 2. 查询 TMDB
        if parsed.type != MediaType.UNKNOWN:
            looked_up = self.lookup.lookup(parsed, hint_type=mtype)
            if looked_up:
                info.tmdb_id = looked_up.tmdb_id
                info.tmdb_info = looked_up.model_dump()

        # 3. 缓存
        self.cache.set(title, info)

        return info

    def identify_batch(self, items: list[dict]) -> list[Optional[MediaInfo]]:
        """批量识别 — 替代 RSS/索引器各自的 ThreadPool"""
        return self.batch.process(items)

    def get_tmdb_info(self, tmdb_id: int, mtype: MediaType) -> dict:
        """直接查询 TMDB 详情"""
        return self.lookup.get_detail(tmdb_id, mtype)
```

---

## 5. 调用方迁移

### 5.1 索引器搜索

当前（`app/indexer/core/batch_identifier.py`）：
```python
# 阶段1: local_filter 中调用 MetaInfo() — 保持不变（本地解析）
meta_info = MetaInfo(title=torrent_name, subtitle=f"{labels} {description}")

# 阶段2: BatchIdentifier.identify() — 改为调用 MediaService.identify_batch()
# 当前: ThreadPoolExecutor + get_media_info()
# 新:   MediaService.identify_batch(candidates)
```

### 5.2 RSS 订阅

当前（`app/services/rss_core.py:193`）：
```python
# 当前: ThreadPoolExecutor(4) + get_media_info()
# 新:   MediaService.identify_batch(all_articles)
```

### 5.3 文件扫描

当前（`app/media/media.py:958`）：
```python
# 当前: get_media_info_on_files() 逐个文件调用 MetaInfo() + TMDB
# 新:   MediaService.identify_batch(file_list)
```

### 5.4 聊天搜索

当前（`app/services/search_torrents.py`）：
```python
# 当前: _media.get_media_info(title=content)
# 新:   media_service.identify(content)
```

---

## 6. 实施步骤

### 阶段1：模型与接口定义（低风险）

1. 创建 `app/media/models.py` — `MediaInfo` pydantic 模型
2. 创建 `app/media/parser/base.py` — `ParserResult`, `BaseParser`
3. 创建 `app/media/lookup/base.py` — `LookupResult`, `BaseLookup`
4. 保持现有 `MetaBase`/`MetaInfo` 不变，新模块并行开发

### 阶段2：Parser 实现（中风险）

1. `RegexParser` — 提取 `MetaAnime`/`MetaVideo` 的核心逻辑
2. `LLMParser` — 包装现有 `MediaRecognizer`
3. 单测验证：同样的输入，新旧 Parser 输出一致

### 阶段3：Lookup 拆分（中风险）

1. `TmdbLookup` — 从 `Media` 类提取所有 TMDB 相关方法
2. `DoubanLookup` — 迁移 `DouBan` 类
3. `BangumiLookup` — 迁移 `Bangumi` 类

### 阶段4：BatchProcessor（中风险）

1. 实现 `BatchProcessor`
2. 在 `app/indexer/core/batch_identifier.py` 中接入
3. 在 `app/services/rss_core.py` 中接入
4. 对比性能：新旧方案处理 100 条数据的时间

### 阶段5：MediaService 门面（高风险）

1. 实现 `MediaService`
2. 迁移所有 `Media().get_media_info()` 调用
3. 删除旧的 `Media` 类（或保留为兼容层）

### 阶段6：清理（低风险）

1. 删除 `MetaBase`/`MetaAnime`/`MetaVideo`（如果已完全迁移）
2. 删除旧的 `BatchIdentifier`（如果已完全迁移）
3. 更新 `app/media/__init__.py`

---

## 7. 兼容性策略

- `MetaInfo()` 工厂函数保留为兼容层，内部委托给 `MediaService.identify()`
- `Media.get_media_info()` 保留为兼容层，标记 `@deprecated`
- `BatchIdentifier` 保留接口，内部改为调用 `BatchProcessor`
- 所有迁移通过单测保证行为一致

---

## 8. 风险与回滚

| 风险 | 缓解措施 |
|------|---------|
| LLM Parser 延迟过高 | 配置项 `agent.media_recognizer_timeout`，超时时 fallback RegexParser |
| Batch 识别失败导致全量 fallback | `BatchProcessor` 内部逐条 fallback，不整体失败 |
| 新 Parser 与旧 Parser 结果不一致 | 单测覆盖 100+ 样本，diff 对比输出 |
| TMDB 查询逻辑拆分引入 bug | 逐方法迁移，每步都有单测 |
