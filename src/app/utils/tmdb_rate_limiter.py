"""
TMDB API 速率限制器
实现令牌桶算法，主动控制请求速率
"""

import threading
import time

import log
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential


class TMDBRateLimiter:
    """
    TMDB API 速率限制器

    TMDB 免费 API 限制：
    - 每秒钟最多 3 个请求
    - 无明确每日上限，但建议合理使用

    使用令牌桶算法实现平滑限流
    """

    def __init__(self, max_requests_per_second: float = 2.5, burst_size: int = 5):
        """
        初始化速率限制器

        :param max_requests_per_second: 每秒最大请求数（默认2.5，略低于限制）
        :param burst_size: 桶容量（突发请求数）
        """
        self._max_rate = max_requests_per_second
        self._burst_size = burst_size
        self._tokens = burst_size  # 当前令牌数
        self._last_update = time.time()
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._wait_count = 0  # 统计等待次数
        self._total_requests = 0  # 总请求数
        self._blocked_requests = 0  # 被限流的请求数

    def acquire(self, timeout: float | None = None) -> bool:
        """
        获取一个请求令牌

        :param timeout: 最大等待时间（秒），None表示无限等待
        :return: 是否成功获取令牌
        """
        with self._condition:
            self._total_requests += 1
            start_time = time.time()

            while True:
                # 更新令牌数
                now = time.time()
                elapsed = now - self._last_update
                self._tokens = min(self._burst_size, self._tokens + elapsed * self._max_rate)
                self._last_update = now

                # 检查是否有可用令牌
                if self._tokens >= 1:
                    self._tokens -= 1
                    return True

                # 计算需要等待的时间
                wait_time = (1 - self._tokens) / self._max_rate

                # 检查是否超时
                if timeout is not None:
                    elapsed_wait = now - start_time
                    if elapsed_wait + wait_time > timeout:
                        self._blocked_requests += 1
                        log.warn(f"[TMDBRateLimiter]获取令牌超时，已等待 {elapsed_wait:.2f} 秒")
                        return False

                self._wait_count += 1
                self._condition.wait(timeout=wait_time)

    def try_acquire(self) -> bool:
        """
        尝试获取令牌，不等待

        :return: 是否成功获取
        """
        with self._lock:
            # 更新令牌数
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(self._burst_size, self._tokens + elapsed * self._max_rate)
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                self._total_requests += 1
                return True
            else:
                self._blocked_requests += 1
                return False

    def get_stats(self) -> dict:
        """
        获取速率限制统计信息

        :return: 统计字典
        """
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "blocked_requests": self._blocked_requests,
                "wait_count": self._wait_count,
                "current_tokens": round(self._tokens, 2),
                "block_rate": round(self._blocked_requests / max(self._total_requests, 1) * 100, 2),
            }

    def reset_stats(self):
        """重置统计信息"""
        with self._lock:
            self._wait_count = 0
            self._total_requests = 0
            self._blocked_requests = 0


def _should_retry_tmdb(exc):
    """判断 TMDB 异常是否应当重试（仅对限流或服务器错误重试）"""
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code is not None and status_code not in [429, 500, 502, 503, 504]:
        return False
    return True


class TMDBRetryWithBackoff:
    """
    TMDB API 指数退避重试机制（基于 tenacity）

    遇到 429 (Too Many Requests) 时，使用指数退避等待后重试
    """

    def __init__(
        self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0, exponential_base: float = 2.0
    ):
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._exponential_base = exponential_base

    def execute(self, func, *args, **kwargs):
        """执行带重试的函数"""

        def _log_retry(retry_state):
            exc = retry_state.outcome.exception()
            wait_time = retry_state.next_action.sleep if retry_state.next_action else 0
            log.warn(f"[TMDBRetry]请求失败，{wait_time:.1f}秒后进行第 {retry_state.attempt_number} 次重试: {exc}")

        for attempt in Retrying(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(
                multiplier=self._base_delay,
                exp_base=self._exponential_base,
                min=self._base_delay,
                max=self._max_delay,
            ),
            retry=retry_if_exception(_should_retry_tmdb),
            before_sleep=_log_retry,
            reraise=True,
        ):
            with attempt:
                return func(*args, **kwargs)
        return None


# 全局速率限制器实例
_global_rate_limiter = TMDBRateLimiter()
_global_retry_handler = TMDBRetryWithBackoff()


def get_rate_limiter() -> TMDBRateLimiter:
    """获取全局速率限制器实例"""
    return _global_rate_limiter


def get_retry_handler() -> TMDBRetryWithBackoff:
    """获取全局重试处理器实例"""
    return _global_retry_handler
