"""API 速率限制器 - Redis/内存双后端滑动窗口实现."""

import threading
import time
from abc import ABC, abstractmethod
from collections import deque

import log
from app.utils.redis_store import RedisStore


class RateLimitBackend(ABC):
    """速率限制后端抽象基类"""

    @abstractmethod
    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """检查 key 在 window 秒内是否未超过 limit 次请求"""


class MemoryBackend(RateLimitBackend):
    """内存滑动窗口后端（线程安全）"""

    def __init__(self):
        self._windows: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window

        with self._lock:
            timestamps = self._windows.get(key)
            if timestamps is None:
                timestamps = deque()
                self._windows[key] = timestamps
            else:
                # 清理过期时间戳
                while timestamps and timestamps[0] < cutoff:
                    timestamps.popleft()

            if len(timestamps) >= limit:
                return False

            timestamps.append(now)
            return True


class RedisBackend(RateLimitBackend):
    """Redis 滑动窗口后端（分布式）"""

    # Lua 脚本：原子清理旧记录 + 计数 + 添加新记录
    _SLIDING_WINDOW_SCRIPT = """
    local key = KEYS[1]
    local window = tonumber(ARGV[1])
    local limit = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local cutoff = now - window

    redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
    local count = redis.call('ZCARD', key)

    if count >= limit then
        return 0
    end

    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window)
    return 1
    """

    def __init__(self):
        self._redis = RedisStore()
        self._script_sha: str | None = None

    def _load_script(self) -> str | None:
        sha = self._redis.script_load(self._SLIDING_WINDOW_SCRIPT)
        return sha

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        if not self._redis.is_available():
            return True  # Redis 不可用时不限流

        now = int(time.time() * 1000)  # 毫秒精度避免碰撞

        try:
            if self._script_sha is None:
                self._script_sha = self._load_script()

            if self._script_sha:
                result = self._redis.evalsha(self._script_sha, 1, key, window * 1000, limit, now)
                return bool(result)
            # Fallback：非原子操作（使用 RedisStore 包装方法）
            cutoff = now - window * 1000
            self._redis.zremrangebyscore(key, 0, cutoff)
            count = self._redis.zcard(key)
            if count >= limit:
                return False
            self._redis.zadd(key, {now: now})
            self._redis.expire(key, window)
            return True
        except Exception as e:
            log.debug(f"RedisBackend 限流检查失败 {key}: {e}")
            return True  # 出错时不限流


class RateLimiter:
    """速率限制器 - 自动选择 Redis/内存后端"""

    def __init__(self):
        redis_backend = RedisBackend()
        if redis_backend._redis.is_available():
            self._backend: RateLimitBackend = redis_backend
            log.info("[RateLimiter]使用 Redis 后端")
        else:
            self._backend = MemoryBackend()
            log.info("[RateLimiter]使用内存后端（Redis 不可用）")

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        return self._backend.is_allowed(key, limit, window)
