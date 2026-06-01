# ADR-008: 通用限流器重构方案

## Status

Proposed

## Date

2026-05-31

## Context

当前系统存在三套独立的限流器，各自为政，无法复用：

| 限流器 | 位置 | 算法 | 后端 | 用途 |
|--------|------|------|------|------|
| `SiteRateLimiter` | `app/sites/site_limiter.py` | 窗口计数（有bug） | 内存 | PT 站点访问限流 |
| `TMDBRateLimiter` | `app/utils/tmdb_rate_limiter.py` | 令牌桶 | 内存 | TMDB API 限流 |
| `RateLimiter` | `app/infrastructure/rate_limiter/` | 滑动窗口 | Redis/内存 | HTTP API 限流（FastAPI 中间件） |

三套限流器代码重复、配置分散、行为不一致。需要统一为通用限流框架，所有限流场景共用同一套实现。

---

## 当前问题

### 问题 1：三套实现，三套配置

```python
# 站点限流配置（site_note JSON 字段）
{"limit_interval": 1, "limit_count": 10, "limit_seconds": 10}

# TMDB 限流配置（硬编码）
TMDBRateLimiter(max_requests_per_second=2.5, burst_size=5)

# API 限流配置（硬编码）
RateLimiter.is_allowed(key="ip:path", limit=100, window=60)
```

### 问题 2：站点限流器计数逻辑严重错误

`site_limiter.py` 的 `last_visit_time` 每次调用都被更新，`count` 几乎无法正确累计，窗口限流基本不生效。

### 问题 3：站点限流是拒绝模式

触发后返回 `True`，调用方直接 `return []` 跳过，导致 RSS/搜索/刷流遗漏资源。

### 问题 4：TMDB 限流器是全局单例

`_global_rate_limiter = TMDBRateLimiter()`，无法按 API Key 区分限流，多 Key 场景下互相干扰。

### 问题 5：API 限流器不支持等待

`is_allowed()` 只返回 True/False，触发限流时直接拒绝请求，无排队等待能力。

### 问题 6：无统一监控

三套限流器各自统计，无法统一查看当前限流状态（哪些 key 在限流、等待队列多长）。

---

## 目标

1. **统一限流框架**：一套代码覆盖站点限流、API 限流、TMDB 限流等所有场景
2. **支持多种算法**：滑动窗口 + 令牌桶，按需选择
3. **支持等待模式**：触发限流时可选排队等待，而非直接拒绝
4. **支持分布式**：Redis 后端确保多实例共享限流状态
5. **统一配置格式**：所有限流场景使用同一套配置语义
6. **统一监控接口**：通过 `/api/system/rate_limits` 查看全局限流状态

---

## 方案设计

### 统一配置格式

所有限流场景使用同一套配置：

```yaml
# 站点配置
site_note:
  rate_limit: "10/m"      # 每分钟 10 次
  rate_burst: 10          # 突发 10 次

# TMDB 配置
tmdb:
  rate_limit: "2.5/s"     # 每秒 2.5 次
  rate_burst: 5           # 突发 5 次

# API 限流配置
api_rate_limits:
  default: "100/m"
  search: "20/m"
  download: "10/m"
```

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    RateLimitEngine                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ SlidingWindow│  │ TokenBucket  │  │ RateLimitMonitor │  │
│  │  (算法)       │  │  (算法)      │  │  (监控/统计)      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘  │
│         │                  │                                │
│         └──────────────────┼────────────────────────────────┘
│                            ▼
│              ┌─────────────────────────┐
│              │   RateLimitBackend      │
│              │  ├─ MemoryBackend       │
│              │  └─ RedisBackend        │
│              └─────────────────────────┘
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐         ┌──────────┐         ┌──────────┐
   │ Site    │         │ TMDB     │         │ API      │
   │ Limiter │         │ Limiter  │         │ Limiter  │
   └─────────┘         └──────────┘         └──────────┘
```

### 核心类设计

```python
# app/infrastructure/rate_limiter/engine.py

class RateLimitEngine:
    """统一限流引擎"""

    def __init__(self, backend: RateLimitBackend):
        self._backend = backend
        self._monitor = RateLimitMonitor()

    def acquire(
        self,
        key: str,
        rate: str = "10/m",
        burst: int | None = None,
        tokens: int = 1,
        timeout: float | None = None,
        algorithm: str = "token_bucket",
    ) -> bool:
        """
        获取执行许可
        :param key: 限流标识（如 site_id、api_key、client_ip）
        :param rate: 速率（如 "10/m", "2.5/s", "100/h"）
        :param burst: 突发容量，默认等于 rate 的数值
        :param tokens: 本次消耗的令牌数
        :param timeout: 最大等待时间（秒），None 表示不等待直接返回
        :param algorithm: "token_bucket" 或 "sliding_window"
        :return: True=获得许可，False=限流中（timeout=None 时）或超时
        """
        ...

    def try_acquire(self, key: str, rate: str = "10/m", tokens: int = 1) -> bool:
        """不等待，立即返回"""
        return self.acquire(key, rate, tokens=tokens, timeout=0)

    def get_status(self, key: str | None = None) -> dict:
        """获取限流状态（用于监控）"""
        ...


# 上下文管理器
@asynccontextmanager
async def rate_limit(
    engine: RateLimitEngine,
    key: str,
    rate: str = "10/m",
    timeout: float | None = 60,
):
    """限流上下文管理器"""
    acquired = await engine.acquire(key, rate, timeout=timeout)
    if not acquired:
        raise RateLimitExceeded(f"Rate limit exceeded for {key}")
    try:
        yield
    finally:
        pass


# 装饰器
def rate_limited(rate: str = "10/m", timeout: float | None = 60):
    """限流装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = _derive_key(func, args, kwargs)
            async with rate_limit(engine, key, rate, timeout):
                return await func(*args, **kwargs)
        return wrapper
    return decorator
```

### 后端实现

```python
# app/infrastructure/rate_limiter/backends.py

class RateLimitBackend(ABC):
    @abstractmethod
    def acquire(
        self, key: str, rate: float, burst: int, tokens: int, timeout: float | None
    ) -> bool:
        """原子化获取许可"""

class MemoryBackend(RateLimitBackend):
    """内存令牌桶（线程安全）"""

    def __init__(self):
        self._buckets: dict[str, dict] = {}  # key -> {tokens, last_update}
        self._lock = threading.Lock()

    def acquire(self, key, rate, burst, tokens, timeout) -> bool:
        deadline = time.time() + timeout if timeout else None
        while True:
            with self._lock:
                bucket = self._buckets.setdefault(key, {"tokens": burst, "last_update": time.time()})
                now = time.time()
                # 填充令牌
                bucket["tokens"] = min(burst, bucket["tokens"] + (now - bucket["last_update"]) * rate)
                bucket["last_update"] = now
                # 尝试消耗
                if bucket["tokens"] >= tokens:
                    bucket["tokens"] -= tokens
                    return True
                # 计算等待时间
                wait_time = (tokens - bucket["tokens"]) / rate
            # 检查超时
            if deadline and time.time() + wait_time > deadline:
                return False
            if timeout == 0:
                return False
            time.sleep(wait_time)

class RedisBackend(RateLimitBackend):
    """Redis 分布式令牌桶（Lua 原子脚本）"""

    _TOKEN_BUCKET_SCRIPT = """
    local key = KEYS[1]
    local rate = tonumber(ARGV[1])
    local burst = tonumber(ARGV[2])
    local tokens = tonumber(ARGV[3])
    local now = tonumber(ARGV[4])
    local timeout_ms = tonumber(ARGV[5])

    local function try_acquire()
        local data = redis.call('HMGET', key, 'tokens', 'last_update')
        local current_tokens = tonumber(data[1]) or burst
        local last_update = tonumber(data[2]) or now

        current_tokens = math.min(burst, current_tokens + (now - last_update) * rate / 1000.0)

        if current_tokens >= tokens then
            current_tokens = current_tokens - tokens
            redis.call('HMSET', key, 'tokens', current_tokens, 'last_update', now)
            redis.call('EXPIRE', key, math.ceil(burst / rate * 1000) + 1)
            return 1
        else
            redis.call('HMSET', key, 'tokens', current_tokens, 'last_update', now)
            return 0
        end
    end

    local deadline = now + timeout_ms
    while true do
        local result = try_acquire()
        if result == 1 then
            return 1
        end
        local remaining = deadline - redis.call('TIME')[1]
        if remaining <= 0 then
            return 0
        end
        -- 简单轮询，实际可用 Redis Pub/Sub 或 Redlock
        redis.call('SET', key .. ':wait', '1', 'PX', math.min(remaining, 100))
    end
    """
```

### 各场景使用方式

#### 1. 站点限流（替换 site_limiter.py）

```python
# app/services/site_rate_limiter.py

@inject
class SiteRateLimiterService:
    def __init__(self, engine: RateLimitEngine, site_repo: ISiteRepository):
        self._engine = engine
        self._site_repo = site_repo

    async def limit(self, site_id: str, timeout: float | None = 60):
        site = self._site_repo.get_by_id(site_id)
        note = json.loads(site.note or "{}")
        rate = note.get("rate_limit", "10/m")
        burst = note.get("rate_burst", _parse_rate(rate)[0])
        return rate_limit(self._engine, key=f"site:{site_id}", rate=rate, burst=burst, timeout=timeout)

# 调用方
async def search(indexer):
    async with site_limiter.limit(indexer.siteid, timeout=60):
        return await do_search(indexer)
```

#### 2. TMDB 限流（替换 tmdb_rate_limiter.py）

```python
# app/utils/tmdb_rate_limiter.py

@inject
class TMDBRateLimiter:
    def __init__(self, engine: RateLimitEngine):
        self._engine = engine

    async def acquire(self, api_key: str | None = None, timeout: float = 30) -> bool:
        # 按 API Key 区分限流，多 Key 互不干扰
        key = f"tmdb:{api_key or 'default'}"
        return await self._engine.acquire(key, rate="2.5/s", burst=5, timeout=timeout)

# 调用方
async def tmdb_request(api_key, ...):
    await tmdb_limiter.acquire(api_key, timeout=30)
    return await http.get(...)
```

#### 3. API 限流（替换现有中间件）

```python
# app/infrastructure/rate_limiter/middleware.py

class RateLimitMiddleware:
    def __init__(self, engine: RateLimitEngine):
        self._engine = engine

    async def __call__(self, request, call_next):
        client_ip = request.client.host
        path = request.url.path
        key = f"api:{client_ip}:{path}"

        # 根据路由配置不同限流规则
        rate = self._get_rate_for_path(path)

        acquired = await self._engine.acquire(key, rate=rate, timeout=0)
        if not acquired:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

        return await call_next(request)
```

### 统一监控

```python
# app/api/routers/system.py

@router.get("/api/system/rate_limits")
async def get_rate_limits(engine: RateLimitEngine = Depends(get_rate_limit_engine)):
    return engine.get_status()
```

返回示例：
```json
{
  "backends": ["redis", "memory"],
  "active_limits": {
    "site:1": {"rate": "10/m", "tokens": 3.5, "queued": 2},
    "site:5": {"rate": "5/m", "tokens": 0, "queued": 5},
    "tmdb:default": {"rate": "2.5/s", "tokens": 1.2, "queued": 0},
    "api:192.168.1.100:/api/search": {"rate": "20/m", "tokens": 18, "queued": 0}
  },
  "total_blocked": 15,
  "total_waited": 120
}
```

---

## 实施步骤

### Phase 1：扩展通用限流引擎

1. **重构 `app/infrastructure/rate_limiter/`**
   - `engine.py` — `RateLimitEngine` 统一引擎
   - `backends.py` — `MemoryBackend` + `RedisBackend`（令牌桶 + 滑动窗口）
   - `decorators.py` — `@rate_limited` 装饰器 + `rate_limit` 上下文管理器
   - `monitor.py` — `RateLimitMonitor` 监控统计

### Phase 2：替换站点限流

3. **创建 `app/services/site_rate_limiter.py`**
   - `SiteRateLimiterService` 封装站点限流逻辑
   - 从 `Sites` 类中解耦

4. **逐个替换调用点**
   - `indexer/client/builtin.py`
   - `rss_core.py`
   - `rss_matcher.py`
   - `brush/helpers.py`
   - `site_subtitle.py`
   - `site_userinfo.py`

5. **删除旧代码**
   - `app/sites/site_limiter.py`
   - `Sites._limiters` / `Sites.check_ratelimit()` / `Sites._rate_limit_val()`

### Phase 3：替换 TMDB 限流

6. **重构 `app/utils/tmdb_rate_limiter.py`**
   - `TMDBRateLimiter` 内部使用 `RateLimitEngine`
   - 支持按 API Key 区分限流
   - 保留 `TMDBRetryWithBackoff`（重试逻辑与限流无关）

### Phase 4：API 限流迁移

7. **重构 `app/infrastructure/rate_limiter/middleware.py` 和 `dependency.py`**
   - 使用 `RateLimitEngine` 替代独立的 `RateLimiter`
   - 支持按路由配置不同限流规则

---

## 决策

等待 review 后按 Phase 逐步实施。

---

## Consequences

### 正面影响

- **代码复用**：一套限流框架覆盖所有场景，消除三套重复代码
- **配置统一**：所有限流场景使用同一套 `rate` + `burst` 配置语义
- **状态可监控**：通过 `/api/system/rate_limits` 查看全局限流状态
- **分布式支持**：Redis 后端确保多实例共享限流状态
- **算法可选**：滑动窗口适合严格计数场景，令牌桶适合平滑流量场景
- **等待模式**：站点限流从拒绝模式改为等待模式，不再遗漏资源

### 负面影响

- **配置迁移**：旧 `limit_interval` / `limit_count` / `limit_seconds` 需迁移到新 `rate` / `burst`
- **异步改造**：等待模式需要调用方支持 async/await
- **Redis 依赖**：分布式限流依赖 Redis，单实例无 Redis 时回退到内存后端
