# -*- coding: utf-8 -*-
"""
统一缓存管理器
管理所有缓存实例，提供统一的访问接口
"""
import threading
from typing import Any, Optional, Dict, List, Type
import log

from .base import CacheAdapter
from .adapters import MemoryCacheAdapter, RedisCacheAdapter, TieredCacheAdapter


class CacheManager:
    """
    统一缓存管理器
    
    特性：
    1. 统一管理多种缓存后端（内存、Redis、分层）
    2. 支持命名空间隔离
    3. 提供缓存统计和监控
    4. 支持批量操作
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._caches: Dict[str, CacheAdapter] = {}
        self._lock = threading.RLock()
        self._initialized = True
        self._default_cache_type = "memory"
        
        log.debug("【CacheManager】缓存管理器初始化完成")
    
    def register(self, name: str, adapter: CacheAdapter) -> 'CacheManager':
        """
        注册缓存实例
        
        :param name: 缓存名称
        :param adapter: 缓存适配器实例
        :return: self，支持链式调用
        """
        with self._lock:
            self._caches[name] = adapter
            log.debug(f"【CacheManager】注册缓存: {name}")
        return self
    
    def create_memory_cache(self, name: str, maxsize: int = 1000) -> 'CacheManager':
        """创建内存缓存"""
        return self.register(name, MemoryCacheAdapter(maxsize=maxsize, name=name))
    
    def create_redis_cache(self, name: str) -> 'CacheManager':
        """创建Redis缓存"""
        return self.register(name, RedisCacheAdapter(name=name))
    
    def create_tiered_cache(self, name: str, memory_maxsize: int = 1000) -> 'CacheManager':
        """创建分层缓存（内存+Redis）"""
        return self.register(name, TieredCacheAdapter(memory_maxsize=memory_maxsize, name=name))
    
    def get(self, name: str) -> Optional[CacheAdapter]:
        """获取指定名称的缓存"""
        with self._lock:
            return self._caches.get(name)
    
    def get_or_create(self, name: str, cache_type: str = "memory", **kwargs) -> CacheAdapter:
        """
        获取或创建缓存
        
        :param name: 缓存名称
        :param cache_type: 缓存类型（memory/redis/tiered）
        :param kwargs: 创建参数
        :return: 缓存适配器
        """
        with self._lock:
            if name not in self._caches:
                if cache_type == "memory":
                    self.create_memory_cache(name, **kwargs)
                elif cache_type == "redis":
                    self.create_redis_cache(name, **kwargs)
                elif cache_type == "tiered":
                    self.create_tiered_cache(name, **kwargs)
                else:
                    raise ValueError(f"不支持的缓存类型: {cache_type}")
            return self._caches[name]
    
    def remove(self, name: str) -> bool:
        """移除缓存"""
        with self._lock:
            if name in self._caches:
                del self._caches[name]
                log.debug(f"【CacheManager】移除缓存: {name}")
                return True
            return False
    
    def clear_all(self) -> None:
        """清空所有缓存"""
        with self._lock:
            for name, cache in self._caches.items():
                try:
                    cache.clear()
                    log.debug(f"【CacheManager】清空缓存: {name}")
                except Exception as e:
                    log.error(f"【CacheManager】清空缓存失败 {name}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取所有缓存统计信息"""
        with self._lock:
            stats = {}
            for name, cache in self._caches.items():
                try:
                    stats[name] = cache.get_stats()
                except Exception as e:
                    stats[name] = {"error": str(e)}
            return stats
    
    def get_all_cache_names(self) -> List[str]:
        """获取所有缓存名称"""
        with self._lock:
            return list(self._caches.keys())
    
    # 便捷的缓存访问方法
    def cache_get(self, cache_name: str, key: str) -> Optional[Any]:
        """从指定缓存获取值"""
        cache = self.get(cache_name)
        if cache:
            return cache.get(key)
        return None
    
    def cache_set(self, cache_name: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置指定缓存的值"""
        cache = self.get(cache_name)
        if cache:
            return cache.set(key, value, ttl)
        return False
    
    def cache_delete(self, cache_name: str, key: str) -> bool:
        """删除指定缓存的键"""
        cache = self.get(cache_name)
        if cache:
            return cache.delete(key)
        return False
    
    def cache_clear(self, cache_name: str) -> bool:
        """清空指定缓存"""
        cache = self.get(cache_name)
        if cache:
            return cache.clear()
        return False
    
    def cache_exists(self, cache_name: str, key: str) -> bool:
        """检查指定缓存中键是否存在"""
        cache = self.get(cache_name)
        if cache:
            return cache.exists(key)
        return False
    
    def cache_keys(self, cache_name: str, pattern: str = "*") -> List[str]:
        """获取指定缓存中匹配模式的键"""
        cache = self.get(cache_name)
        if cache:
            return cache.keys(pattern)
        return []
