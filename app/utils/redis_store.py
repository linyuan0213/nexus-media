import json
from typing import Any, Optional, List

import log
from app.core.constants import REDIS_HOST, REDIS_PORT


class RedisStore:
    """
    Redis 客户端包装器

    特性：
    1. 惰性连接：首次使用时才建立连接
    2. 自动降级：Redis 不可用时静默失败，不阻塞业务
    3. 连接健康检查：每次操作前检查连接状态
    """

    def __init__(self):
        self._client = None
        self._available = False

    def _ensure_connection(self) -> bool:
        """确保 Redis 连接可用，返回是否可用"""
        if self._available and self._client is not None:
            try:
                self._client.ping()
                return True
            except Exception:
                self._available = False
                self._client = None

        if self._client is None:
            try:
                import redis
                self._client = redis.StrictRedis(
                    host=REDIS_HOST, port=REDIS_PORT, db=0,
                    socket_connect_timeout=2, socket_timeout=2
                )
                self._client.ping()
                self._available = True
                log.debug("RedisStore 连接成功")
                return True
            except Exception as e:
                self._client = None
                self._available = False
                log.debug(f"RedisStore 连接失败: {e}")
                return False

        return self._available

    def is_available(self) -> bool:
        """检查 Redis 是否可用"""
        return self._ensure_connection()

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        """设置键值对，可设置过期时间(秒)"""
        if not self._ensure_connection():
            return
        try:
            self._client.set(key, value, ex=ex)
        except Exception as e:
            log.debug(f"RedisStore set 失败 {key}: {e}")

    def get(self, key: str) -> Optional[Any]:
        """获取键值"""
        if not self._ensure_connection():
            return None
        try:
            return self._client.get(key)
        except Exception as e:
            log.debug(f"RedisStore get 失败 {key}: {e}")
            return None

    def hset(self, name: str, key: str, value: Any) -> None:
        """设置哈希字段"""
        if not self._ensure_connection():
            return
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self._client.hset(name, key, value)
        except Exception as e:
            log.debug(f"RedisStore hset 失败 {name}/{key}: {e}")

    def hget(self, name: str, key: str) -> Optional[Any]:
        """获取哈希字段值"""
        if not self._ensure_connection():
            return None
        try:
            return self._client.hget(name, key)
        except Exception as e:
            log.debug(f"RedisStore hget 失败 {name}/{key}: {e}")
            return None

    def hdel(self, name: str, key: str) -> None:
        """删除哈希字段"""
        if not self._ensure_connection():
            return
        try:
            self._client.hdel(name, key)
        except Exception as e:
            log.debug(f"RedisStore hdel 失败 {name}/{key}: {e}")

    def hgetall(self, name: str) -> dict:
        """获取所有哈希字段"""
        if not self._ensure_connection():
            return {}
        try:
            return {k.decode('utf-8'): self.hget(name, k) for k in self._client.hkeys(name)}
        except Exception as e:
            log.debug(f"RedisStore hgetall 失败 {name}: {e}")
            return {}

    def lpush(self, name: str, *values: Any) -> None:
        """列表左推入"""
        if not self._ensure_connection():
            return
        try:
            self._client.lpush(
                name,
                *[json.dumps(v) if isinstance(v, (dict, list)) else v for v in values]
            )
        except Exception as e:
            log.debug(f"RedisStore lpush 失败 {name}: {e}")

    def rpop(self, name: str) -> Optional[Any]:
        """列表右弹出"""
        if not self._ensure_connection():
            return None
        try:
            return self._client.rpop(name)
        except Exception as e:
            log.debug(f"RedisStore rpop 失败 {name}: {e}")
            return None

    def rpush(self, name: str, *values: Any) -> None:
        """列表右推入"""
        if not self._ensure_connection():
            return
        try:
            self._client.rpush(
                name,
                *[json.dumps(v) if isinstance(v, (dict, list)) else v for v in values]
            )
        except Exception as e:
            log.debug(f"RedisStore rpush 失败 {name}: {e}")

    def lpop(self, name: str) -> Optional[Any]:
        """列表左弹出"""
        if not self._ensure_connection():
            return None
        try:
            return self._client.lpop(name)
        except Exception as e:
            log.debug(f"RedisStore lpop 失败 {name}: {e}")
            return None

    def llen(self, name: str) -> int:
        """获取列表长度"""
        if not self._ensure_connection():
            return 0
        try:
            return self._client.llen(name)
        except Exception as e:
            log.debug(f"RedisStore llen 失败 {name}: {e}")
            return 0

    def delete(self, *keys: str) -> None:
        """删除键"""
        if not self._ensure_connection():
            return
        try:
            self._client.delete(*keys)
        except Exception as e:
            log.debug(f"RedisStore delete 失败 {keys}: {e}")

    def ping(self) -> bool:
        """测试连接"""
        return self._ensure_connection()

    def keys(self, pattern: str) -> List[str]:
        """查找匹配模式的键"""
        if not self._ensure_connection():
            return []
        try:
            return [k.decode('utf-8') for k in self._client.keys(pattern)]
        except Exception as e:
            log.debug(f"RedisStore keys 失败 {pattern}: {e}")
            return []

    def expire(self, key: str, seconds: int) -> None:
        """设置键过期时间"""
        if not self._ensure_connection():
            return
        try:
            self._client.expire(key, seconds)
        except Exception as e:
            log.debug(f"RedisStore expire 失败 {key}: {e}")

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self._ensure_connection():
            return False
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            log.debug(f"RedisStore exists 失败 {key}: {e}")
            return False

    def ttl(self, key: str) -> int:
        """获取键的剩余生存时间(秒)"""
        if not self._ensure_connection():
            return -2
        try:
            return self._client.ttl(key)
        except Exception as e:
            log.debug(f"RedisStore ttl 失败 {key}: {e}")
            return -2

    # ---------- Redis Stream (可靠消息队列) ----------

    def xadd(self, stream: str, fields: dict, max_len: int = 10000) -> Optional[str]:
        """向 Stream 添加消息，返回消息 ID"""
        if not self._ensure_connection():
            return None
        try:
            return self._client.xadd(stream, fields, maxlen=max_len, approximate=True)
        except Exception as e:
            log.debug(f"RedisStore xadd 失败 {stream}: {e}")
            return None

    def xgroup_create(self, stream: str, group: str, mkstream: bool = True) -> bool:
        """创建消费者组"""
        if not self._ensure_connection():
            return False
        try:
            self._client.xgroup_create(stream, group, id="0", mkstream=mkstream)
            return True
        except Exception as e:
            if "already exists" in str(e):
                return True
            log.debug(f"RedisStore xgroup_create 失败 {stream}/{group}: {e}")
            return False

    def xreadgroup(self, group: str, consumer: str, streams: dict, count: int = 1,
                   block: int = 5000) -> list:
        """消费者组读取消息
        :param streams: {stream_name: ">"} 表示只读新消息
        :return: [(stream_name, [(msg_id, {field: value})])]
        """
        if not self._ensure_connection():
            return []
        try:
            result = self._client.xreadgroup(group, consumer, streams, count=count,
                                             block=block)
            return result or []
        except Exception as e:
            log.debug(f"RedisStore xreadgroup 失败: {e}")
            return []

    def xack(self, stream: str, group: str, *ids: str) -> int:
        """确认消息已处理，返回确认的条数"""
        if not self._ensure_connection():
            return 0
        try:
            return self._client.xack(stream, group, *ids)
        except Exception as e:
            log.debug(f"RedisStore xack 失败 {stream}: {e}")
            return 0

    def xpending(self, stream: str, group: str) -> int:
        """获取 Pending 列表中的消息数"""
        if not self._ensure_connection():
            return 0
        try:
            info = self._client.xpending(stream, group)
            return info.get("pending", 0) if isinstance(info, dict) else 0
        except Exception as e:
            log.debug(f"RedisStore xpending 失败 {stream}: {e}")
            return 0

    def xclaim(self, stream: str, group: str, consumer: str, min_idle_time: int,
               *ids: str) -> list:
        """认领超时未确认的消息（用于重试）"""
        if not self._ensure_connection():
            return []
        try:
            return self._client.xclaim(stream, group, consumer, min_idle_time, ids)
        except Exception as e:
            log.debug(f"RedisStore xclaim 失败 {stream}: {e}")
            return []

    def xdel(self, stream: str, *ids: str) -> int:
        """删除 Stream 中的消息"""
        if not self._ensure_connection():
            return 0
        try:
            return self._client.xdel(stream, *ids)
        except Exception as e:
            log.debug(f"RedisStore xdel 失败 {stream}: {e}")
            return 0
