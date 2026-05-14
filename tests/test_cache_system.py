"""
统一缓存系统测试 - 独立测试，不依赖项目配置
"""

import os
import sys
import threading
import time

import pytest

# 直接导入缓存模块，绕过 app.utils 的初始化
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 独立导入缓存模块
from app.infrastructure.cache_system.adapters import MemoryCacheAdapter
from app.infrastructure.cache_system.base import CacheEntry
from app.infrastructure.cache_system.cache_manager import CacheManager
from app.infrastructure.cache_system.decorators import cached, cached_with_lock, lru_cache_with_ttl
from app.infrastructure.cache_system.utils import CacheKeyBuilder


class TestCacheEntry:
    """测试缓存条目"""

    def test_cache_entry_creation(self):
        """测试缓存条目创建"""
        entry = CacheEntry("value", ttl=60)
        assert entry.value == "value"
        assert entry.ttl == 60
        assert entry.created_at > 0

    def test_cache_entry_no_ttl(self):
        """测试无TTL的缓存条目"""
        entry = CacheEntry("value")
        assert entry.ttl is None
        assert not entry.is_expired()

    def test_cache_entry_expired(self):
        """测试过期的缓存条目"""
        entry = CacheEntry("value", ttl=0)
        time.sleep(0.01)
        assert entry.is_expired()

    def test_cache_entry_remaining_ttl(self):
        """测试获取剩余TTL"""
        entry = CacheEntry("value", ttl=60)
        remaining = entry.get_remaining_ttl()
        assert 0 <= remaining <= 60

        # 无TTL的情况
        entry_no_ttl = CacheEntry("value")
        assert entry_no_ttl.get_remaining_ttl() == -1


class TestMemoryCacheAdapter:
    """测试内存缓存适配器"""

    @pytest.fixture
    def cache(self):
        return MemoryCacheAdapter(maxsize=100, name="test")

    def test_basic_set_get(self, cache):
        """测试基本的set和get"""
        assert cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent(self, cache):
        """测试获取不存在的键"""
        assert cache.get("nonexistent") is None

    def test_delete(self, cache):
        """测试删除"""
        cache.set("key1", "value1")
        assert cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        """测试删除不存在的键"""
        assert not cache.delete("nonexistent")

    def test_exists(self, cache):
        """测试存在性检查"""
        cache.set("key1", "value1")
        assert cache.exists("key1")
        assert not cache.exists("key2")

    def test_ttl(self, cache):
        """测试TTL"""
        cache.set("key1", "value1", ttl=2)
        assert cache.ttl("key1") > 0
        assert cache.ttl("key1") <= 2

        # 等待过期
        time.sleep(2.1)
        assert cache.ttl("key1") == -2

    def test_expire(self, cache):
        """测试设置过期时间"""
        cache.set("key1", "value1")
        assert cache.expire("key1", 2)
        assert cache.ttl("key1") > 0

    def test_expire_nonexistent(self, cache):
        """测试对不存在的键设置过期时间"""
        assert not cache.expire("nonexistent", 10)

    def test_clear(self, cache):
        """测试清空"""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_keys(self, cache):
        """测试获取键列表"""
        cache.set("prefix:key1", "value1")
        cache.set("prefix:key2", "value2")
        cache.set("other:key3", "value3")

        all_keys = cache.keys()
        assert len(all_keys) == 3

        prefix_keys = cache.keys("prefix:*")
        assert len(prefix_keys) == 2

    def test_lru_eviction(self, cache):
        """测试LRU淘汰"""
        # 设置较小的maxsize
        cache._maxsize = 3

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # 应该淘汰key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_lru_order(self, cache):
        """测试LRU顺序"""
        cache._maxsize = 3

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # 访问key1，使其变为最近使用
        cache.get("key1")

        # 添加新键，应该淘汰key2
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_stats(self, cache):
        """测试统计信息"""
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss

        stats = cache.get_stats()
        assert stats["name"] == "test"
        assert stats["type"] == "memory"
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_complex_values(self, cache):
        """测试复杂类型的值"""
        # 字典
        cache.set("dict", {"a": 1, "b": [1, 2, 3]})
        assert cache.get("dict") == {"a": 1, "b": [1, 2, 3]}

        # 列表
        cache.set("list", [1, 2, 3, {"nested": True}])
        assert cache.get("list") == [1, 2, 3, {"nested": True}]

        # None值
        cache.set("none", None)
        assert cache.get("none") is None


class TestCacheManager:
    """测试缓存管理器"""

    @pytest.fixture
    def manager(self):
        # 重置单例
        CacheManager._instance = None
        return CacheManager()

    def test_singleton(self, manager):
        """测试单例模式"""
        manager2 = CacheManager()
        assert manager is manager2

    def test_create_memory_cache(self, manager):
        """测试创建内存缓存"""
        manager.create_memory_cache("test_memory", maxsize=100)
        cache = manager.get("test_memory")
        assert cache is not None

    def test_get_or_create(self, manager):
        """测试获取或创建"""
        cache1 = manager.get_or_create("dynamic", "memory", maxsize=50)
        cache2 = manager.get_or_create("dynamic", "memory", maxsize=50)
        assert cache1 is cache2

    def test_remove(self, manager):
        """测试移除缓存"""
        manager.create_memory_cache("to_remove")
        assert manager.remove("to_remove")
        assert not manager.remove("to_remove")

    def test_cache_operations(self, manager):
        """测试缓存操作"""
        manager.create_memory_cache("ops")

        # 设置值
        assert manager.cache_set("ops", "key1", "value1")
        # 获取值
        assert manager.cache_get("ops", "key1") == "value1"
        # 检查存在
        assert manager.cache_exists("ops", "key1")
        # 删除
        assert manager.cache_delete("ops", "key1")
        # 清空
        assert manager.cache_clear("ops")

    def test_get_all_names(self, manager):
        """测试获取所有缓存名称"""
        manager.create_memory_cache("cache1")
        manager.create_memory_cache("cache2")
        names = manager.get_all_cache_names()
        assert "cache1" in names
        assert "cache2" in names

    def test_clear_all(self, manager):
        """测试清空所有缓存"""
        manager.create_memory_cache("cache1")
        manager.create_memory_cache("cache2")

        manager.cache_set("cache1", "key", "value")
        manager.cache_set("cache2", "key", "value")

        manager.clear_all()

        assert manager.cache_get("cache1", "key") is None
        assert manager.cache_get("cache2", "key") is None


class TestDecorators:
    """测试装饰器"""

    @pytest.fixture
    def cache(self):
        return MemoryCacheAdapter(maxsize=100, name="decorator_test")

    def test_cached_decorator(self, cache):
        """测试缓存装饰器"""
        call_count = 0

        @cached(cache_instance=cache, ttl=60)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # 第一次调用
        result1 = test_func(5)
        assert result1 == 10
        assert call_count == 1

        # 第二次调用，应该使用缓存
        result2 = test_func(5)
        assert result2 == 10
        assert call_count == 1  # 不应该再调用

    def test_cached_with_lock(self, cache):
        """测试带锁的缓存装饰器"""
        call_count = 0

        @cached_with_lock(cache_instance=cache, ttl=60)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = test_func(5)
        result2 = test_func(5)

        assert result1 == result2 == 10
        assert call_count == 1

    def test_lru_cache_with_ttl(self):
        """测试带TTL的LRU缓存"""
        call_count = 0

        @lru_cache_with_ttl(maxsize=100, ttl=60)
        def test_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        test_func(5)
        test_func(5)
        assert call_count == 1

        # 测试缓存信息
        stats = test_func.cache_info()
        assert stats["type"] == "memory"


class TestCacheUtils:
    """测试缓存工具"""

    def test_key_builder_simple(self):
        """测试简单键构建"""
        key = CacheKeyBuilder.simple("part1", "part2", "part3")
        assert key == "part1:part2:part3"

    def test_key_builder_with_prefix(self):
        """测试带前缀的键构建"""
        key = CacheKeyBuilder.with_prefix("prefix", "part1", "part2")
        assert key == "prefix:part1:part2"

    def test_key_builder_from_func(self):
        """测试从函数构建键"""

        def test_func(self, arg1, arg2, kwarg1=None):
            pass

        key = CacheKeyBuilder.from_func(test_func, "obj", "val1", "val2", kwarg1="kw1")
        assert "test_func" in key
        assert "val1" in key
        assert "val2" in key
        assert "kwarg1=kw1" in key

    def test_key_builder_typed(self):
        """测试带类型的键构建"""

        # 模拟MediaType
        class MockMediaType:
            def __init__(self, value):
                self.value = value

        media_type = MockMediaType("movie")
        key = CacheKeyBuilder.typed("tmdb", media_type, "123", "zh")
        assert key == "tmdb:movie:123:zh"


class TestConcurrency:
    """测试并发安全性"""

    def test_concurrent_access(self):
        """测试并发访问"""
        cache = MemoryCacheAdapter(maxsize=1000)
        errors = []

        def worker(n):
            try:
                for i in range(100):
                    cache.set(f"key_{n}_{i}", f"value_{i}")
                    cache.get(f"key_{n}_{i}")
                    cache.exists(f"key_{n}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_cached_with_lock_concurrent(self):
        """测试带锁装饰器的并发"""
        cache = MemoryCacheAdapter(maxsize=100)
        call_count = [0]
        lock = threading.Lock()

        @cached_with_lock(cache_instance=cache)
        def expensive_operation(x):
            with lock:
                call_count[0] += 1
            time.sleep(0.01)  # 模拟耗时操作
            return x * 2

        results = []

        def worker():
            results.append(expensive_operation(5))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 虽然并发调用，但只有一个实际执行
        assert call_count[0] == 1
        assert all(r == 10 for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
