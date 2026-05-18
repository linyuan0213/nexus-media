# 统一缓存系统文档

## 概述

本文档描述了 Nexus Media 项目中统一缓存系统的架构和使用方法。该系统整合了项目中分散的多种缓存实现，提供了一致、可扩展的缓存接口。

## 架构设计

### 核心组件

```
app/utils/cache_system/
├── __init__.py          # 模块入口，导出主要组件
├── base.py              # 基础接口定义
├── adapters.py          # 缓存适配器实现
├── cache_manager.py     # 统一缓存管理器
├── caches.py            # 专用缓存类
├── decorators.py        # 缓存装饰器
├── utils.py             # 工具函数
└── compat.py            # 兼容旧接口
```

### 缓存类型

系统支持三种主要的缓存后端：

1. **内存缓存 (MemoryCacheAdapter)**
   - 基于LRU算法的本地内存缓存
   - 适用于高频访问、小数据量的缓存场景
   - 支持TTL过期机制

2. **Redis缓存 (RedisCacheAdapter)**
   - 基于Redis的分布式缓存
   - 适用于多实例部署场景
   - 支持数据持久化

3. **分层缓存 (TieredCacheAdapter)**
   - L1内存 + L2 Redis的两级缓存
   - 自动维护缓存一致性
   - 兼顾性能和可靠性

## 快速开始

### 1. 使用缓存管理器

```python
from app.utils.cache_system import get_cache_manager

# 获取全局缓存管理器
cache_manager = get_cache_manager()

# 创建内存缓存
cache_manager.create_memory_cache("my_cache", maxsize=1000)

# 基本操作
cache_manager.cache_set("my_cache", "key", "value", ttl=3600)
value = cache_manager.cache_get("my_cache", "key")
cache_manager.cache_delete("my_cache", "key")
```

### 2. 使用装饰器

```python
from app.utils.cache_system import cached
from app.utils.cache_system.adapters import MemoryCacheAdapter

# 创建缓存实例
cache = MemoryCacheAdapter(maxsize=100)

@cached(cache_instance=cache, ttl=3600)
def get_user(user_id):
    # 这个函数的结果会被缓存
    return User.query.get(user_id)

# 清除缓存
get_user.cache_clear()
```

### 3. 使用专用缓存

```python
from app.utils.cache_system import TMDBCache, MediaInfoCache

# TMDB专用缓存
tmdb_cache = TMDBCache()
tmdb_cache.set_tmdb_info(MediaType.MOVIE, "123", movie_info)
info = tmdb_cache.get_tmdb_info(MediaType.MOVIE, "123")

# 媒体信息缓存
media_cache = MediaInfoCache()
media_cache.set("key", value, ttl=3600)
```

## API参考

### CacheAdapter 接口

所有缓存适配器都实现了以下接口：

```python
class CacheAdapter:
    def get(self, key: str) -> Optional[Any]
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool
    def delete(self, key: str) -> bool
    def exists(self, key: str) -> bool
    def clear(self) -> bool
    def keys(self, pattern: str = "*") -> List[str]
    def ttl(self, key: str) -> int  # -2:不存在, -1:永不过期, >=0:剩余秒数
    def expire(self, key: str, seconds: int) -> bool
    def get_stats(self) -> Dict[str, Any]
```

### 装饰器

#### @cached

基础缓存装饰器：

```python
@cached(cache_instance=cache, key_func=None, ttl=3600)
def my_function(arg):
    return expensive_operation(arg)
```

参数：
- `cache_instance`: 缓存实例或缓存名称
- `key_func`: 自定义缓存键生成函数
- `ttl`: 过期时间（秒）

#### @cached_with_lock

带锁的缓存装饰器，防止缓存穿透：

```python
@cached_with_lock(cache_instance=cache, lock=None, ttl=3600)
def my_function(arg):
    return expensive_operation(arg)
```

#### @lru_cache_with_ttl

兼容functools.lru_cache风格的装饰器：

```python
@lru_cache_with_ttl(maxsize=128, ttl=3600)
def my_function(arg):
    return expensive_operation(arg)
```

### 缓存管理器

```python
# 创建缓存
cache_manager.create_memory_cache(name, maxsize=1000)
cache_manager.create_redis_cache(name)
cache_manager.create_tiered_cache(name, memory_maxsize=1000)

# 获取缓存
cache = cache_manager.get(name)
cache = cache_manager.get_or_create(name, cache_type="memory")

# 批量操作
cache_manager.clear_all()
stats = cache_manager.get_stats()
```

## 专用缓存

### TMDBCache

专门用于TMDB数据缓存：

```python
cache = TMDBCache()

# 缓存TMDB详情
cache.set_tmdb_info(mtype, tmdbid, info, language="zh")
cache.get_tmdb_info(mtype, tmdbid, language="zh")

# 缓存媒体信息
cache.set_media_info(title, info, year, mtype)
cache.get_media_info(title, year, mtype)

# 缓存季详情
cache.set_season_info(tmdbid, season, info)
cache.get_season_info(tmdbid, season)

# 缓存演员信息
cache.set_person_info(person_id, info)
cache.get_person_info(person_id)

# 缓存趋势
cache.set_trending(media_type, time_window, page, info)
cache.get_trending(media_type, time_window, page)

# 清除缓存
cache.clear_tmdb_cache(tmdbid)
cache.clear_media_cache(title)
```

### 其他专用缓存

- `TokenCache`: Token缓存
- `ConfigLoadCache`: 配置加载缓存
- `CategoryLoadCache`: 分类加载缓存
- `OpenAISessionCache`: OpenAI会话缓存
- `MediaInfoCache`: 媒体信息缓存
- `SearchResultCache`: 搜索结果缓存
- `SiteInfoCache`: 站点信息缓存

## 缓存键命名规范

推荐使用以下格式：

```
prefix:type:id:subid
```

例如：
- `tmdb:movie:123:zh`
- `media:Test Movie:2024:movie`
- `tmdb:season:123:1`

使用 `CacheKeyBuilder` 工具类：

```python
from app.utils.cache_system import CacheKeyBuilder

# 简单键
key = CacheKeyBuilder.simple("part1", "part2")  # "part1:part2"

# 带前缀
key = CacheKeyBuilder.with_prefix("tmdb", "movie", "123")  # "tmdb:movie:123"

# 带类型
key = CacheKeyBuilder.typed("tmdb", MediaType.MOVIE, "123", "zh")
```

## 缓存预热

系统启动时可自动执行缓存预热，提前加载热点数据到缓存中。

### 使用方法

```python
from app.utils import warm_cache_on_startup

# 系统启动时调用
warm_cache_on_startup(async_mode=False)  # 同步模式
warm_cache_on_startup(async_mode=True)   # 异步模式
```

### 自定义预热器

```python
from app.utils.cache_system import CacheWarmer, get_warmer_manager

class MyCacheWarmer(CacheWarmer):
    def __init__(self):
        super().__init__("my_warmer", priority=5)
    
    def warm(self) -> bool:
        # 加载数据到缓存
        cache = get_cache_manager().get("my_cache")
        data = load_data_from_db()
        cache.set("key", data)
        return True

# 注册预热器
manager = get_warmer_manager()
manager.register(MyCacheWarmer())

# 执行预热
manager.warm_all()
```

### 内置预热器

| 预热器 | 优先级 | 说明 |
|--------|--------|------|
| ConfigCacheWarmer | 0 | 系统配置数据 |
| SiteCacheWarmer | 1 | 站点配置信息 |
| WordsCacheWarmer | 2 | 识别词配置 |
| TMDBTrendingWarmer | 3 | TMDB热门数据 |

### 获取预热状态

```python
from app.utils import get_warmer_manager

status = get_warmer_manager().get_status()
print(status)
```

## 最佳实践

### 1. 选择合适的缓存类型

| 场景 | 推荐缓存类型 | 说明 |
|------|-------------|------|
| 配置数据 | MemoryCache | 数据量小，访问频繁 |
| TMDB数据 | RedisCache | 数据量大，需要共享 |
| 用户会话 | MemoryCache | 时效性要求高 |
| 搜索结果 | TieredCache | 兼顾性能和一致性 |

### 2. 设置合理的TTL

```python
# TMDB数据 - 变化不频繁
tmdb_cache.set_tmdb_info(mtype, tmdbid, info, ttl=7*24*3600)  # 7天

# 搜索结果 - 适中
cache.set("search_result", result, ttl=1800)  # 30分钟

# 配置数据 - 较短
cache.set("config", config, ttl=60)  # 1分钟
```

### 3. 缓存键设计

```python
# 好的键设计
key = f"user:{user_id}:profile"
key = f"movie:{tmdbid}:zh"

# 避免使用动态数据
# 不好：key = f"search:{datetime.now()}"
# 更好：key = f"search:{query_hash}"
```

### 4. 错误处理

```python
try:
    value = cache.get(key)
    if value is None:
        value = expensive_operation()
        cache.set(key, value, ttl=3600)
except Exception as e:
    # 缓存失败时直接执行
    value = expensive_operation()
```

## 迁移指南

### 从 functools.lru_cache 迁移

```python
# 旧代码
from functools import lru_cache

@lru_cache(maxsize=256)
def get_data(key):
    return fetch_data(key)

# 新代码
from app.utils.cache_system import lru_cache_with_ttl

@lru_cache_with_ttl(maxsize=256, ttl=3600)
def get_data(key):
    return fetch_data(key)
```

### 从 cachetools 迁移

```python
# 旧代码
from cachetools import cached, TTLCache

@cached(cache=TTLCache(maxsize=128, ttl=60))
def query_data(key):
    return db.query(key)

# 新代码
from app.utils.cache_system import cached
from app.utils.cache_system.adapters import MemoryCacheAdapter

cache = MemoryCacheAdapter(maxsize=128)

@cached(cache_instance=cache, ttl=60)
def query_data(key):
    return db.query(key)
```

### 从旧版 TMDBCache 迁移

```python
# 旧代码
from app.utils.tmdb_cache import TMDBCache
cache = TMDBCache()

# 新代码
from app.utils.cache_system import TMDBCache, get_cache_manager
cache = TMDBCache(get_cache_manager().get("tmdb"))
```

## 监控和调试

### 查看缓存统计

```python
# 单个缓存统计
stats = cache.get_stats()
print(f"命中率: {stats['hit_rate']}")
print(f"大小: {stats['size']}/{stats['maxsize']}")

# 所有缓存统计
all_stats = cache_manager.get_stats()
for name, stat in all_stats.items():
    print(f"{name}: {stat}")
```

### 日志输出

缓存系统会自动输出调试日志：

```
[Cache] 缓存命中: tmdb:movie:123:zh
[Cache] 缓存设置: media:Test Movie:2024:movie
[CacheManager] 注册缓存: tmdb
```

## 注意事项

1. **内存缓存的数据不会持久化**，重启后会丢失
2. **Redis缓存需要Redis服务支持**，确保Redis配置正确
3. **分层缓存的一致性**，L1和L2之间可能存在短暂不一致
4. **缓存键大小**，Redis键有大小限制（512MB），避免使用过大的键
5. **值序列化**，复杂对象会自动序列化，确保对象可序列化

## 性能测试

运行缓存系统测试：

```bash
# 运行所有缓存测试
NEXUS_MEDIA_CONFIG=/path/to/config.yaml uv run pytest tests/test_cache_system.py -v

# 运行特定测试
NEXUS_MEDIA_CONFIG=/path/to/config.yaml uv run pytest tests/test_cache_system.py::TestMemoryCacheAdapter -v
```

## 缓存事件系统

支持监听缓存变更事件，实现缓存数据的同步和通知。

### 事件类型

| 事件类型 | 说明 |
|----------|------|
| `SET` | 数据被设置 |
| `GET` | 数据被获取 |
| `DELETE` | 数据被删除 |
| `EXPIRE` | 数据过期 |
| `CLEAR` | 缓存被清空 |
| `HIT` | 缓存命中 |
| `MISS` | 缓存未命中 |
| `EVICT` | 数据被驱逐(LRU) |

### 使用装饰器监听事件

```python
from app.utils.cache_system import on_cache_event, CacheEventType

@on_cache_event({CacheEventType.SET, CacheEventType.DELETE}, "tmdb:*")
def handle_tmdb_cache_events(event):
    print(f"TMDB缓存变更: {event.event_type.name} - {event.key}")
```

### 使用事件管理器

```python
from app.utils.cache_system import get_event_manager, CacheEventType

manager = get_event_manager()

def my_listener(event):
    print(f"收到事件: {event.event_type.name}")

# 添加监听器
manager.add_listener(
    my_listener,
    event_types={CacheEventType.SET, CacheEventType.DELETE},
    cache_name_pattern="*"
)

# 移除监听器
manager.remove_listener(my_listener)
```

### 全局监听器

```python
# 监听所有缓存事件
def global_listener(event):
    print(f"[Global] {event.cache_name}: {event.event_type.name}")

manager.add_listener(global_listener)  # 不指定event_types即为全局监听
```

### 事件数据结构

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

@dataclass
class CacheEvent:
    event_type: CacheEventType  # 事件类型
    cache_name: str             # 缓存名称
    key: Optional[str] = None   # 缓存键
    value: Any = None           # 缓存值
    ttl: Optional[int] = None   # 过期时间
    timestamp: datetime         # 事件时间
```
