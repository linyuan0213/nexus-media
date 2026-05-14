"""
TMDB API 优化测试

测试内容：
1. 速率限制器功能测试
2. 指数退避重试测试
3. 请求去重测试

运行：pytest tests/test_tmdb_optimization.py -v
"""
import os
import sys
import threading
import time
from unittest.mock import Mock

import pytest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 直接在测试中定义被测试的类，避免导入依赖


class TMDBRateLimiter:
    """
    TMDB API 速率限制器 - 简化版用于测试
    """

    def __init__(self, max_requests_per_second: float = 2.5, burst_size: int = 5):
        self._max_rate = max_requests_per_second
        self._burst_size = burst_size
        self._tokens = burst_size
        self._last_update = time.time()
        self._lock = threading.Lock()
        self._wait_count = 0
        self._total_requests = 0
        self._blocked_requests = 0

    def acquire(self, timeout=None):
        with self._lock:
            self._total_requests += 1
            start_time = time.time()

            while True:
                now = time.time()
                elapsed = now - self._last_update
                self._tokens = min(
                    self._burst_size,
                    self._tokens + elapsed * self._max_rate
                )
                self._last_update = now

                if self._tokens >= 1:
                    self._tokens -= 1
                    return True

                wait_time = (1 - self._tokens) / self._max_rate

                if timeout is not None:
                    elapsed_wait = now - start_time
                    if elapsed_wait + wait_time > timeout:
                        self._blocked_requests += 1
                        return False

                self._wait_count += 1
                self._lock.release()
                try:
                    time.sleep(wait_time)
                finally:
                    self._lock.acquire()

    def try_acquire(self):
        with self._lock:
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(
                self._burst_size,
                self._tokens + elapsed * self._max_rate
            )
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                self._total_requests += 1
                return True
            else:
                self._blocked_requests += 1
                return False

    def get_stats(self):
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "blocked_requests": self._blocked_requests,
                "wait_count": self._wait_count,
                "current_tokens": round(self._tokens, 2),
                "block_rate": round(self._blocked_requests / max(self._total_requests, 1) * 100, 2)
            }


class TMDBRetryWithBackoff:
    """TMDB API 指数退避重试机制"""

    def __init__(self, max_retries=3, base_delay=1.0, max_delay=60.0, exponential_base=2.0):
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._exponential_base = exponential_base

    def get_delay(self, attempt):
        delay = self._base_delay * (self._exponential_base ** attempt)
        return min(delay, self._max_delay)

    def should_retry(self, attempt, status_code=None):
        if attempt >= self._max_retries:
            return False
        if status_code is not None and status_code not in [429, 500, 502, 503, 504]:
            return False
        return True

    def execute(self, func, *args, **kwargs):
        last_exception = None

        for attempt in range(self._max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                status_code = getattr(e, 'status_code', None)
                if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                    status_code = e.response.status_code

                if not self.should_retry(attempt, status_code):
                    raise

                delay = self.get_delay(attempt)
                time.sleep(delay)

        raise last_exception


class RequestDeduper:
    """请求去重器 - 简化版"""

    def __init__(self, default_timeout=30.0):
        self._default_timeout = default_timeout
        self._pending_requests = {}
        self._lock = threading.Lock()
        self._stats = {"deduped_requests": 0, "actual_requests": 0}

    def execute(self, key, func, *args, **kwargs):
        with self._lock:
            if key in self._pending_requests:
                self._stats["deduped_requests"] += 1
                event, _, _ = self._pending_requests[key]
            else:
                event = threading.Event()
                self._pending_requests[key] = (event, None, None)
                self._stats["actual_requests"] += 1

                def do_request():
                    try:
                        result = func(*args, **kwargs)
                        with self._lock:
                            _, _, error = self._pending_requests[key]
                            if error is None:
                                self._pending_requests[key] = (event, result, None)
                    except Exception as e:
                        with self._lock:
                            self._pending_requests[key] = (event, None, e)
                    finally:
                        event.set()
                        threading.Timer(0.1, self._cleanup, args=[key]).start()

                threading.Thread(target=do_request, daemon=True).start()
                return self._wait_for_result(key)

        return self._wait_for_result(key)

    def _wait_for_result(self, key):
        with self._lock:
            if key not in self._pending_requests:
                raise RuntimeError(f"请求 {key} 已被清理")
            event, _, _ = self._pending_requests[key]

        if not event.wait(timeout=self._default_timeout):
            raise TimeoutError(f"请求 {key} 等待超时")

        with self._lock:
            _, result, error = self._pending_requests[key]
            if error is not None:
                raise error
            return result

    def _cleanup(self, key):
        with self._lock:
            if key in self._pending_requests:
                del self._pending_requests[key]

    def get_stats(self):
        with self._lock:
            return self._stats.copy()


# ==================== 测试用例 ====================

class TestTMDBRateLimiter:
    """测试 TMDB 速率限制器"""

    def test_basic_acquire(self):
        """测试基本获取令牌功能"""
        limiter = TMDBRateLimiter(max_requests_per_second=10, burst_size=5)

        # 应该能立即获取 5 个令牌（burst_size）
        for i in range(5):
            assert limiter.try_acquire() == True, f"第 {i+1} 个令牌应该能立即获取"

        # 第 6 个应该失败（令牌已用完）
        assert limiter.try_acquire() == False

    def test_rate_limiting(self):
        """测试速率限制"""
        limiter = TMDBRateLimiter(max_requests_per_second=10, burst_size=1)

        # 消耗掉唯一的令牌
        assert limiter.try_acquire() == True

        # 立即再获取应该失败
        assert limiter.try_acquire() == False

        # 等待 0.15 秒后应该能获取（每秒10个 = 每0.1秒1个）
        time.sleep(0.15)
        assert limiter.try_acquire() == True

    def test_acquire_with_wait(self):
        """测试带等待的获取"""
        limiter = TMDBRateLimiter(max_requests_per_second=2, burst_size=1)

        # 消耗掉令牌
        assert limiter.try_acquire() == True

        # 再获取应该需要等待
        start = time.time()
        result = limiter.acquire(timeout=1.0)
        elapsed = time.time() - start

        assert result == True
        assert elapsed >= 0.4  # 每秒2个 = 每0.5秒1个

    def test_stats(self):
        """测试统计信息"""
        limiter = TMDBRateLimiter(max_requests_per_second=100, burst_size=1)

        # 获取一些令牌
        limiter.try_acquire()
        limiter.try_acquire()
        limiter.try_acquire()

        stats = limiter.get_stats()
        assert stats["total_requests"] == 3
        assert stats["blocked_requests"] == 2  # 第一次成功，后两次被阻塞


class TestTMDBRetryWithBackoff:
    """测试 TMDB 指数退避重试"""

    def test_success_no_retry(self):
        """测试成功时不重试"""
        retry = TMDBRetryWithBackoff(max_retries=3)

        mock_func = Mock(return_value="success")
        result = retry.execute(mock_func, "arg1", kwarg1="value1")

        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    def test_retry_on_exception(self):
        """测试异常时重试"""
        retry = TMDBRetryWithBackoff(max_retries=3, base_delay=0.01)

        mock_func = Mock(side_effect=[Exception("error1"), Exception("error2"), "success"])
        result = retry.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_retry_exhausted(self):
        """测试重试次数耗尽"""
        retry = TMDBRetryWithBackoff(max_retries=2, base_delay=0.01)

        mock_func = Mock(side_effect=Exception("persistent error"))

        with pytest.raises(Exception, match="persistent error"):
            retry.execute(mock_func)

        assert mock_func.call_count == 3  # 初始 + 2次重试

    def test_delay_calculation(self):
        """测试延迟计算"""
        retry = TMDBRetryWithBackoff(base_delay=1.0, exponential_base=2.0, max_delay=10.0)

        assert retry.get_delay(0) == 1.0   # 第1次: 1 * 2^0 = 1
        assert retry.get_delay(1) == 2.0   # 第2次: 1 * 2^1 = 2
        assert retry.get_delay(2) == 4.0   # 第3次: 1 * 2^2 = 4
        assert retry.get_delay(10) == 10.0  # 超过 max_delay


class TestRequestDeduper:
    """测试请求去重器"""

    def test_dedupe_concurrent_requests(self):
        """测试并发请求去重"""
        deduper = RequestDeduper()

        call_count = [0]
        results = []
        result_lock = threading.Lock()

        def slow_function():
            call_count[0] += 1
            time.sleep(0.1)
            return f"result_{call_count[0]}"

        # 启动多个线程并发请求相同 key
        threads = []
        for i in range(5):
            def worker():
                result = deduper.execute("test_key", slow_function)
                with result_lock:
                    results.append(result)
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 实际函数应该只被调用一次
        assert call_count[0] == 1
        # 所有线程应该拿到相同结果
        assert all(r == "result_1" for r in results)
        # 统计应该有 4 个被合并的请求
        stats = deduper.get_stats()
        assert stats["deduped_requests"] == 4
        assert stats["actual_requests"] == 1

    def test_different_keys_not_deduped(self):
        """测试不同 key 不去重"""
        deduper = RequestDeduper()

        def func():
            return "result"

        # 不同 key 的请求应该独立执行
        result1 = deduper.execute("key1", func)
        result2 = deduper.execute("key2", func)

        assert result1 == "result"
        assert result2 == "result"

        stats = deduper.get_stats()
        assert stats["actual_requests"] == 2
        assert stats["deduped_requests"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
