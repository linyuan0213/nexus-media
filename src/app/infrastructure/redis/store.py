"""Redis 存储 — 连接管理与键值/哈希/列表/有序集合/Stream 操作."""

import json
from typing import Any

from redis import StrictRedis
from redis.exceptions import RedisError

import log
from app.core.constants import REDIS_HOST, REDIS_PORT


class RedisStore:
    def __init__(self):
        self._client: StrictRedis | None = None
        self._available = False

    def _ensure_connection(self) -> StrictRedis | None:
        if self._available and self._client is not None:
            try:
                self._client.ping()
                return self._client
            except RedisError:
                self._available = False
                self._client = None

        if self._client is None:
            try:
                self._client = StrictRedis(
                    host=REDIS_HOST, port=int(REDIS_PORT), db=0, socket_connect_timeout=5, socket_timeout=10
                )
                self._client.ping()
                self._available = True
                log.debug("RedisStore 连接成功")
                return self._client
            except RedisError as e:
                self._client = None
                self._available = False
                log.debug(f"RedisStore 连接失败: {e}")
                return None

        return self._client

    def is_available(self) -> bool:
        """检查 Redis 是否可用"""
        return self._ensure_connection() is not None

    def set(self, key: str, value: Any, ex: int | None = None) -> None:
        """设置键值对，可设置过期时间(秒)"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            client.set(key, value, ex=ex)
        except RedisError as e:
            log.debug(f"RedisStore set 失败 {key}: {e}")

    def get(self, key: str) -> Any | None:
        """获取键值"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            return client.get(key)
        except RedisError as e:
            log.debug(f"RedisStore get 失败 {key}: {e}")
            return None

    def hset(self, name: str, key: str, value: Any) -> None:
        """设置哈希字段"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            client.hset(name, key, value)
        except RedisError as e:
            log.debug(f"RedisStore hset 失败 {name}/{key}: {e}")

    def hget(self, name: str, key: str) -> Any | None:
        """获取哈希字段值"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            return client.hget(name, key)
        except RedisError as e:
            log.debug(f"RedisStore hget 失败 {name}/{key}: {e}")
            return None

    def hdel(self, name: str, key: str) -> None:
        """删除哈希字段"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            client.hdel(name, key)
        except RedisError as e:
            log.debug(f"RedisStore hdel 失败 {name}/{key}: {e}")

    def hgetall(self, name: str) -> dict:
        """获取所有哈希字段"""
        client = self._ensure_connection()
        if client is None:
            return {}
        try:
            raw_keys = client.hkeys(name)
            if not isinstance(raw_keys, list):
                return {}
            return {k.decode("utf-8"): self.hget(name, k.decode("utf-8")) for k in raw_keys if isinstance(k, bytes)}
        except RedisError as e:
            log.debug(f"RedisStore hgetall 失败 {name}: {e}")
            return {}

    def lpush(self, name: str, *values: Any) -> None:
        """列表左推入"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            client.lpush(name, *[json.dumps(v) if isinstance(v, (dict, list)) else v for v in values])
        except RedisError as e:
            log.debug(f"RedisStore lpush 失败 {name}: {e}")

    def rpop(self, name: str) -> Any | None:
        """列表右弹出"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            return client.rpop(name)
        except RedisError as e:
            log.debug(f"RedisStore rpop 失败 {name}: {e}")
            return None

    def rpush(self, name: str, *values: Any) -> None:
        """列表右推入"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            client.rpush(name, *[json.dumps(v) if isinstance(v, (dict, list)) else v for v in values])
        except RedisError as e:
            log.debug(f"RedisStore rpush 失败 {name}: {e}")

    def lpop(self, name: str) -> Any | None:
        """列表左弹出"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            return client.lpop(name)
        except RedisError as e:
            log.debug(f"RedisStore lpop 失败 {name}: {e}")
            return None

    def llen(self, name: str) -> int:
        """获取列表长度"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            result = client.llen(name)
            return result if isinstance(result, int) else 0
        except RedisError as e:
            log.debug(f"RedisStore llen 失败 {name}: {e}")
            return 0

    def delete(self, *keys: str) -> None:
        """删除键"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            client.delete(*keys)
        except RedisError as e:
            log.debug(f"RedisStore delete 失败 {keys}: {e}")

    def ping(self) -> bool:
        """测试连接"""
        return self._ensure_connection() is not None

    def keys(self, pattern: str) -> list[str]:
        """查找匹配模式的键"""
        client = self._ensure_connection()
        if client is None:
            return []
        try:
            raw_keys = client.keys(pattern)
            if not isinstance(raw_keys, list):
                return []
            return [k.decode("utf-8") for k in raw_keys if isinstance(k, bytes)]
        except RedisError as e:
            log.debug(f"RedisStore keys 失败 {pattern}: {e}")
            return []

    def expire(self, key: str, seconds: int) -> None:
        """设置键过期时间"""
        client = self._ensure_connection()
        if client is None:
            return
        try:
            client.expire(key, seconds)
        except RedisError as e:
            log.debug(f"RedisStore expire 失败 {key}: {e}")

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        client = self._ensure_connection()
        if client is None:
            return False
        try:
            return bool(client.exists(key))
        except RedisError as e:
            log.debug(f"RedisStore exists 失败 {key}: {e}")
            return False

    def script_load(self, script: str) -> str | None:
        """加载 Lua 脚本并返回 SHA1 摘要"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            result = client.script_load(script)
            return str(result) if result is not None else None
        except RedisError as e:
            log.debug(f"RedisStore script_load 失败: {e}")
            return None

    def evalsha(self, sha: str, numkeys: int, *keys_and_args) -> Any | None:
        """通过 SHA1 执行已加载的 Lua 脚本"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            return client.evalsha(sha, numkeys, *keys_and_args)
        except RedisError as e:
            log.debug(f"RedisStore evalsha 失败 {sha}: {e}")
            return None

    def zremrangebyscore(self, name: str, min_score: float, max_score: float) -> int:
        """删除有序集合中指定分数范围的成员"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            result = client.zremrangebyscore(name, min_score, max_score)
            return result if isinstance(result, int) else 0
        except RedisError as e:
            log.debug(f"RedisStore zremrangebyscore 失败 {name}: {e}")
            return 0

    def zcard(self, name: str) -> int:
        """获取有序集合的成员数"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            result = client.zcard(name)
            return result if isinstance(result, int) else 0
        except RedisError as e:
            log.debug(f"RedisStore zcard 失败 {name}: {e}")
            return 0

    def zadd(self, name: str, mapping: dict) -> int:
        """向有序集合添加成员"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            result = client.zadd(name, mapping)
            return result if isinstance(result, int) else 0
        except RedisError as e:
            log.debug(f"RedisStore zadd 失败 {name}: {e}")
            return 0

    def ttl(self, key: str) -> int:
        """获取键的剩余生存时间(秒)"""
        client = self._ensure_connection()
        if client is None:
            return -2
        try:
            result = client.ttl(key)
            return result if isinstance(result, int) else -2
        except RedisError as e:
            log.debug(f"RedisStore ttl 失败 {key}: {e}")
            return -2

    # ---------- Redis Stream (可靠消息队列) ----------

    def xadd(self, stream: str, fields: dict, max_len: int = 10000) -> str | None:
        """向 Stream 添加消息，返回消息 ID"""
        client = self._ensure_connection()
        if client is None:
            return None
        try:
            result = client.xadd(stream, fields, maxlen=max_len, approximate=True)
            return str(result) if result is not None and not isinstance(result, list) else None
        except RedisError as e:
            log.debug(f"RedisStore xadd 失败 {stream}: {e}")
            return None

    def xgroup_create(self, stream: str, group: str, mkstream: bool = True) -> bool:
        """创建消费者组"""
        client = self._ensure_connection()
        if client is None:
            return False
        try:
            client.xgroup_create(stream, group, id="0", mkstream=mkstream)
            return True
        except RedisError as e:
            if "already exists" in str(e):
                return True
            log.debug(f"RedisStore xgroup_create 失败 {stream}/{group}: {e}")
            return False

    def xreadgroup(self, group: str, consumer: str, streams: dict, count: int = 1, block: int = 5000) -> list:
        """消费者组读取消息
        :param streams: {stream_name: ">"} 表示只读新消息
        :return: [(stream_name, [(msg_id, {field: value})])]
        """
        client = self._ensure_connection()
        if client is None:
            return []
        try:
            result = client.xreadgroup(group, consumer, streams, count=count, block=block)
            return result if isinstance(result, list) else []
        except RedisError as e:
            log.debug(f"RedisStore xreadgroup 失败: {e}")
            return []

    def xack(self, stream: str, group: str, *ids: str) -> int:
        """确认消息已处理，返回确认的条数"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            result = client.xack(stream, group, *ids)
            return result if isinstance(result, int) else 0
        except RedisError as e:
            log.debug(f"RedisStore xack 失败 {stream}: {e}")
            return 0

    def xpending(self, stream: str, group: str) -> int:
        """获取 Pending 列表中的消息数"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            info = client.xpending(stream, group)
            return info.get("pending", 0) if isinstance(info, dict) else 0
        except RedisError as e:
            log.debug(f"RedisStore xpending 失败 {stream}: {e}")
            return 0

    def xclaim(self, stream: str, group: str, consumer: str, min_idle_time: int, *ids: str) -> list:
        """认领超时未确认的消息（用于重试）"""
        client = self._ensure_connection()
        if client is None:
            return []
        try:
            result = client.xclaim(stream, group, consumer, min_idle_time, ids)
            return result if isinstance(result, list) else []
        except RedisError as e:
            log.debug(f"RedisStore xclaim 失败 {stream}: {e}")
            return []

    def xdel(self, stream: str, *ids: str) -> int:
        """删除 Stream 中的消息"""
        client = self._ensure_connection()
        if client is None:
            return 0
        try:
            result = client.xdel(stream, *ids)
            return result if isinstance(result, int) else 0
        except RedisError as e:
            log.debug(f"RedisStore xdel 失败 {stream}: {e}")
            return 0
