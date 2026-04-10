# -*- coding: utf-8 -*-
"""
缓存适配器实现
支持内存缓存和Redis缓存
"""
import threading
import pickle
from typing import Any, Optional, List, Dict, OrderedDict
from collections import OrderedDict
import log

from .base import CacheAdapter, CacheEntry
from .events import CacheEventManager, CacheEvent, CacheEventType


# 获取事件管理器实例
_event_manager = CacheEventManager()

def get_cache_value(cache_adapter, key: str) -> Any:
    """
    获取缓存值，返回 (found, value) 元组
    found: True 表示缓存命中，False 表示缓存未命中
    value: 缓存值（当 found 为 True 时）
    """
    value = cache_adapter.get(key)
    if value is None:
        # 检查是缓存不存在/过期，还是缓存值就是 None
        if not cache_adapter.exists(key):
            return False, None
    return True, value


class MemoryCacheAdapter(CacheAdapter):
    """内存缓存适配器 - 使用LRU策略"""
    
    def __init__(self, maxsize: int = 1000, name: str = "memory"):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._maxsize = maxsize
        self._name = name
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0
        }
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                # 触发MISS事件
                _event_manager.emit(CacheEvent(
                    event_type=CacheEventType.MISS,
                    cache_name=self._name,
                    key=key
                ))
                return None
            
            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                # 触发EXPIRE事件
                _event_manager.emit(CacheEvent(
                    event_type=CacheEventType.EXPIRE,
                    cache_name=self._name,
                    key=key
                ))
                return None
            
            # LRU: 移动到末尾（最近使用）
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            # 触发GET和HIT事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.GET,
                cache_name=self._name,
                key=key,
                value=entry.value
            ))
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.HIT,
                cache_name=self._name,
                key=key,
                value=entry.value
            ))
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        with self._lock:
            # 如果键已存在，先删除以便更新位置
            if key in self._cache:
                del self._cache[key]
            
            # 检查是否需要淘汰
            evicted = False
            while len(self._cache) >= self._maxsize:
                self._evict_oldest()
                evicted = True
            
            self._cache[key] = CacheEntry(value, ttl)
            self._stats["sets"] += 1
            
            # 触发SET事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.SET,
                cache_name=self._name,
                key=key,
                value=value,
                ttl=ttl
            ))
            
            # 如果发生了驱逐，触发EVICT事件
            if evicted:
                _event_manager.emit(CacheEvent(
                    event_type=CacheEventType.EVICT,
                    cache_name=self._name
                ))
            
            return True
    
    def _evict_oldest(self):
        """淘汰最旧的条目"""
        if self._cache:
            oldest_key = next(iter(self._cache))
            oldest_entry = self._cache[oldest_key]
            del self._cache[oldest_key]
            self._stats["evictions"] += 1
            # 触发EVICT事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.EVICT,
                cache_name=self._name,
                key=oldest_key,
                value=oldest_entry.value
            ))
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                del self._cache[key]
                self._stats["deletes"] += 1
                # 触发DELETE事件
                _event_manager.emit(CacheEvent(
                    event_type=CacheEventType.DELETE,
                    cache_name=self._name,
                    key=key,
                    value=entry.value
                ))
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True
    
    def clear(self) -> bool:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            # 触发CLEAR事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.CLEAR,
                cache_name=self._name
            ))
            return True
    
    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        import fnmatch
        with self._lock:
            # 清理过期条目
            expired_keys = [
                k for k, e in self._cache.items() if e.is_expired()
            ]
            for k in expired_keys:
                del self._cache[k]
            
            if pattern == "*":
                return list(self._cache.keys())
            return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
    
    def ttl(self, key: str) -> int:
        """获取键的剩余生存时间"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return -2
            return entry.get_remaining_ttl()
    
    def expire(self, key: str, seconds: int) -> bool:
        """设置键的过期时间"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None or entry.is_expired():
                return False
            entry.ttl = seconds
            entry.created_at = __import__('time').time()
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0
            return {
                "name": self._name,
                "type": "memory",
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": f"{hit_rate:.2%}",
                "sets": self._stats["sets"],
                "deletes": self._stats["deletes"],
                "evictions": self._stats["evictions"]
            }


class RedisCacheAdapter(CacheAdapter):
    """Redis缓存适配器"""
    
    def __init__(self, name: str = "redis"):
        self._name = name
        self._redis = None
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0
        }
        self._lock = threading.Lock()
        self._init_redis()
    
    def _init_redis(self):
        """初始化Redis连接"""
        try:
            from app.utils.redis_store import RedisStore
            self._redis = RedisStore()
            # 测试连接
            self._redis.ping()
            log.debug(f"【Cache】Redis适配器初始化成功")
        except Exception as e:
            log.warn(f"【Cache】Redis适配器初始化失败: {e}")
            self._redis = None
    
    def _ensure_connection(self) -> bool:
        """确保Redis连接可用"""
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except:
            # 尝试重连
            self._init_redis()
            return self._redis is not None
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if not self._ensure_connection():
            return None
        
        try:
            data = self._redis.get(key)
            if data is None:
                with self._lock:
                    self._stats["misses"] += 1
                # 触发MISS事件
                _event_manager.emit(CacheEvent(
                    event_type=CacheEventType.MISS,
                    cache_name=self._name,
                    key=key
                ))
                return None
            
            # 尝试反序列化
            try:
                value = pickle.loads(data)
            except:
                value = data
            
            with self._lock:
                self._stats["hits"] += 1
            
            # 触发HIT事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.HIT,
                cache_name=self._name,
                key=key,
                value=value
            ))
            return value
        except Exception as e:
            log.error(f"【Cache】Redis获取缓存失败 {key}: {e}")
            with self._lock:
                self._stats["errors"] += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        if not self._ensure_connection():
            return False
        
        try:
            # 序列化值
            data = pickle.dumps(value)
            self._redis.set(key, data, ex=ttl)
            with self._lock:
                self._stats["sets"] += 1
            
            # 触发SET事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.SET,
                cache_name=self._name,
                key=key,
                value=value,
                ttl=ttl
            ))
            return True
        except Exception as e:
            log.error(f"【Cache】Redis设置缓存失败 {key}: {e}")
            with self._lock:
                self._stats["errors"] += 1
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        if not self._ensure_connection():
            return False
        
        try:
            self._redis.delete(key)
            with self._lock:
                self._stats["deletes"] += 1
            
            # 触发DELETE事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.DELETE,
                cache_name=self._name,
                key=key
            ))
            return True
        except Exception as e:
            log.error(f"【Cache】Redis删除缓存失败 {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self._ensure_connection():
            return False
        
        try:
            return self._redis.exists(key)
        except Exception as e:
            log.error(f"【Cache】Redis检查键存在失败 {key}: {e}")
            return False
    
    def clear(self) -> bool:
        """清空所有缓存（仅清除以 'cache:' 开头的键）"""
        if not self._ensure_connection():
            return False
        
        try:
            keys = self._redis.keys("cache:*")
            if keys:
                self._redis.delete(*keys)
            
            # 触发CLEAR事件
            _event_manager.emit(CacheEvent(
                event_type=CacheEventType.CLEAR,
                cache_name=self._name
            ))
            return True
        except Exception as e:
            log.error(f"【Cache】Redis清空缓存失败: {e}")
            return False
    
    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        if not self._ensure_connection():
            return []
        
        try:
            return self._redis.keys(pattern)
        except Exception as e:
            log.error(f"【Cache】Redis获取键列表失败: {e}")
            return []
    
    def ttl(self, key: str) -> int:
        """获取键的剩余生存时间"""
        if not self._ensure_connection():
            return -2
        
        try:
            return self._redis.ttl(key)
        except Exception as e:
            log.error(f"【Cache】Redis获取TTL失败 {key}: {e}")
            return -2
    
    def expire(self, key: str, seconds: int) -> bool:
        """设置键的过期时间"""
        if not self._ensure_connection():
            return False
        
        try:
            self._redis.expire(key, seconds)
            return True
        except Exception as e:
            log.error(f"【Cache】Redis设置过期时间失败 {key}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0
            return {
                "name": self._name,
                "type": "redis",
                "connected": self._redis is not None,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": f"{hit_rate:.2%}",
                "sets": self._stats["sets"],
                "deletes": self._stats["deletes"],
                "errors": self._stats["errors"]
            }


class TieredCacheAdapter(CacheAdapter):
    """分层缓存适配器 - L1(内存) + L2(Redis)"""
    
    def __init__(self, memory_maxsize: int = 1000, name: str = "tiered"):
        self._l1 = MemoryCacheAdapter(maxsize=memory_maxsize, name=f"{name}_l1")
        self._l2 = RedisCacheAdapter(name=f"{name}_l2")
        self._name = name
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0
        }
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值 - 先查L1，再查L2"""
        # 先查L1
        value = self._l1.get(key)
        if value is not None:
            self._stats["l1_hits"] += 1
            return value
        
        # 再查L2
        value = self._l2.get(key)
        if value is not None:
            self._stats["l2_hits"] += 1
            # 回填L1
            self._l1.set(key, value)
            return value
        
        self._stats["misses"] += 1
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值 - 同时设置L1和L2"""
        l1_result = self._l1.set(key, value, ttl)
        l2_result = self._l2.set(key, value, ttl)
        return l1_result or l2_result
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        l1_result = self._l1.delete(key)
        l2_result = self._l2.delete(key)
        return l1_result or l2_result
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return self._l1.exists(key) or self._l2.exists(key)
    
    def clear(self) -> bool:
        """清空所有缓存"""
        l1_result = self._l1.clear()
        l2_result = self._l2.clear()
        return l1_result and l2_result
    
    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        # 合并L1和L2的键
        l1_keys = set(self._l1.keys(pattern))
        l2_keys = set(self._l2.keys(pattern))
        return list(l1_keys | l2_keys)
    
    def ttl(self, key: str) -> int:
        """获取键的剩余生存时间"""
        # 优先使用L1的TTL
        l1_ttl = self._l1.ttl(key)
        if l1_ttl >= 0:
            return l1_ttl
        return self._l2.ttl(key)
    
    def expire(self, key: str, seconds: int) -> bool:
        """设置键的过期时间"""
        l1_result = self._l1.expire(key, seconds)
        l2_result = self._l2.expire(key, seconds)
        return l1_result or l2_result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = sum(self._stats.values())
        return {
            "name": self._name,
            "type": "tiered",
            "l1": self._l1.get_stats(),
            "l2": self._l2.get_stats(),
            "l1_hits": self._stats["l1_hits"],
            "l2_hits": self._stats["l2_hits"],
            "misses": self._stats["misses"],
            "total_requests": total
        }
