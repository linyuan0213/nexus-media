"""
请求去重器 - 合并对相同资源的并发请求

使用场景：当多个地方同时请求相同的 TMDB ID 时，
只发送一个实际请求，其他请求等待结果共享
"""
import threading
from collections.abc import Callable
from functools import wraps
from typing import Any

import log


class RequestDeduper:
    """
    请求去重器

    核心原则：锁内只做 O(1) 的内存操作，绝不在持有锁期间
    调用任何可能阻塞的函数（event.wait、网络请求、数据库查询等）。
    """

    def __init__(self, default_timeout: float = 30.0):
        self._default_timeout = default_timeout
        self._pending_requests: dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._stats = {
            "deduped_requests": 0,
            "actual_requests": 0,
            "cache_hits": 0
        }

    def execute(self, key: str, func: Callable, *args, **kwargs) -> Any:
        """
        执行去重后的请求

        流程：
        1. 锁内快速判断：key 是否存在
        2. 立即释放锁
        3. 重复请求 → 锁外等待共享结果
        4. 新请求 → 锁外执行实际函数
        """
        need_wait = False

        with self._lock:
            if key in self._pending_requests:
                self._stats["deduped_requests"] += 1
                need_wait = True
                log.debug(f"【RequestDeduper】检测到重复请求，等待共享结果: {key}")
            else:
                event = threading.Event()
                self._pending_requests[key] = (event, None, None)
                self._stats["actual_requests"] += 1
                log.debug(f"【RequestDeduper】开始执行请求: {key}")

        # 必须在完全释放锁后再进入可能阻塞的分支
        if need_wait:
            return self._wait_for_result(key)

        # 在锁外执行实际请求
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._pending_requests[key] = (event, result, None)
            event.set()
            return result
        except Exception as e:
            with self._lock:
                self._pending_requests[key] = (event, None, e)
            event.set()
            raise
        finally:
            threading.Timer(5.0, self._cleanup, args=[key]).start()

    def _wait_for_result(self, key: str) -> Any:
        """等待请求完成并返回结果（全程遵循"锁内不阻塞"原则）"""
        # 阶段1：极短时间加锁，仅获取 event 引用
        with self._lock:
            if key not in self._pending_requests:
                raise RuntimeError(f"请求 {key} 已被清理")
            event, _, _ = self._pending_requests[key]

        # 阶段2：完全在锁外等待，不会阻塞其他任何线程
        if not event.wait(timeout=self._default_timeout):
            raise TimeoutError(f"请求 {key} 等待超时")

        # 阶段3：再次极短时间加锁，读取结果
        with self._lock:
            if key not in self._pending_requests:
                raise RuntimeError(f"请求 {key} 已被清理")
            _, result, error = self._pending_requests[key]
            if error is not None:
                raise error
            return result

    def _cleanup(self, key: str):
        """清理已完成的请求"""
        with self._lock:
            if key in self._pending_requests:
                del self._pending_requests[key]

    def get_stats(self) -> dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()

    def reset_stats(self):
        """重置统计信息"""
        with self._lock:
            self._stats = {
                "deduped_requests": 0,
                "actual_requests": 0,
                "cache_hits": 0
            }


# 全局去重器实例
_global_deduper = RequestDeduper()


def get_deduper() -> RequestDeduper:
    """获取全局请求去重器"""
    return _global_deduper


def dedupe_tmdb_request(func: Callable) -> Callable:
    """
    装饰器：对 TMDB 请求进行去重

    使用方法：
        @dedupe_tmdb_request
        def get_tmdb_info(self, tmdbid):
            return self.tmdb.details(tmdbid)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        key_parts = [func.__name__]
        for arg in args[1:] if args else []:
            key_parts.append(str(arg))
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        key = ":".join(key_parts)

        deduper = get_deduper()
        return deduper.execute(key, func, *args, **kwargs)

    return wrapper
