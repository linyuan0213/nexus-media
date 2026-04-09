# -*- coding: utf-8 -*-
"""
请求去重器 - 合并对相同资源的并发请求

使用场景：当多个地方同时请求相同的 TMDB ID 时，
只发送一个实际请求，其他请求等待结果共享
"""
import threading
import time
from typing import Any, Optional, Callable, Dict
from functools import wraps
import log


class RequestDeduper:
    """
    请求去重器
    
    通过缓存正在进行的请求，避免对相同资源的重复请求
    """
    
    def __init__(self, default_timeout: float = 30.0):
        """
        初始化请求去重器
        
        :param default_timeout: 默认等待超时时间（秒）
        """
        self._default_timeout = default_timeout
        # 存储正在进行的请求: {key: (event, result, error)}
        self._pending_requests: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._stats = {
            "deduped_requests": 0,  # 被合并的请求数
            "actual_requests": 0,   # 实际发出的请求数
            "cache_hits": 0         # 从 pending 缓存中命中的次数
        }
    
    def execute(self, key: str, func: Callable, *args, **kwargs) -> Any:
        """
        执行去重后的请求
        
        :param key: 请求的唯一标识
        :param func: 实际执行的函数
        :param args: 函数位置参数
        :param kwargs: 函数关键字参数
        :return: 函数返回值
        :raises: 函数抛出的异常
        """
        # 首先检查是否已有相同的请求在进行中
        with self._lock:
            if key in self._pending_requests:
                # 有相同请求在进行，等待其结果
                self._stats["deduped_requests"] += 1
                event, _, _ = self._pending_requests[key]
                log.debug(f"【RequestDeduper】检测到重复请求，等待共享结果: {key}")
            else:
                # 没有相同请求，创建新的请求
                event = threading.Event()
                self._pending_requests[key] = (event, None, None)
                self._stats["actual_requests"] += 1
                log.debug(f"【RequestDeduper】发起新请求: {key}")
                
                # 在锁外执行实际请求
                def do_request():
                    try:
                        result = func(*args, **kwargs)
                        with self._lock:
                            _, _, error = self._pending_requests[key]
                            if error is None:  # 如果没有被异常中断
                                self._pending_requests[key] = (event, result, None)
                    except Exception as e:
                        with self._lock:
                            self._pending_requests[key] = (event, None, e)
                    finally:
                        event.set()
                        # 清理 pending 请求（延迟清理，确保其他线程能获取结果）
                        threading.Timer(0.1, self._cleanup, args=[key]).start()
                
                # 启动后台线程执行请求
                threading.Thread(target=do_request, daemon=True).start()
                return self._wait_for_result(key)
        
        # 等待共享结果
        return self._wait_for_result(key)
    
    def _wait_for_result(self, key: str) -> Any:
        """等待请求完成并返回结果"""
        with self._lock:
            if key not in self._pending_requests:
                raise RuntimeError(f"请求 {key} 已被清理")
            event, _, _ = self._pending_requests[key]
        
        # 等待事件（在锁外等待以避免阻塞）
        if not event.wait(timeout=self._default_timeout):
            raise TimeoutError(f"请求 {key} 等待超时")
        
        with self._lock:
            _, result, error = self._pending_requests[key]
            if error is not None:
                raise error
            return result
    
    def _cleanup(self, key: str):
        """清理已完成的请求"""
        with self._lock:
            if key in self._pending_requests:
                del self._pending_requests[key]
    
    def get_stats(self) -> Dict[str, int]:
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
        # 生成唯一 key
        key_parts = [func.__name__]
        # 添加 args（跳过 self）
        for arg in args[1:] if args else []:
            key_parts.append(str(arg))
        # 添加 kwargs
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        key = ":".join(key_parts)
        
        deduper = get_deduper()
        return deduper.execute(key, func, *args, **kwargs)
    
    return wrapper
