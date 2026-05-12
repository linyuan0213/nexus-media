# -*- coding: utf-8 -*-
"""
缓存系统基础接口定义
"""
from abc import ABC, abstractmethod
from typing import Any, Optional, List, Dict, Union
import time


class CacheAdapter(ABC):
    """缓存适配器基类"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值
        :param key: 缓存键
        :param value: 缓存值
        :param ttl: 过期时间（秒），None表示永不过期
        :return: 是否设置成功
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存"""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """清空所有缓存"""
        pass
    
    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        pass
    
    @abstractmethod
    def ttl(self, key: str) -> int:
        """
        获取键的剩余生存时间
        :return: >=0 剩余秒数, -1 永不过期, -2 键不存在
        """
        pass
    
    @abstractmethod
    def expire(self, key: str, seconds: int) -> bool:
        """设置键的过期时间"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        pass


class CacheEntry:
    """缓存条目"""
    
    def __init__(self, value: Any, ttl: Optional[int] = None):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def get_remaining_ttl(self) -> int:
        """获取剩余生存时间
        
        Returns:
            >=0: 剩余秒数
            -1: 永不过期
            -2: 已过期或不存在
        """
        if self.ttl is None:
            return -1
        remaining = int(self.ttl - (time.time() - self.created_at))
        if remaining <= 0:
            return -2
        return remaining
