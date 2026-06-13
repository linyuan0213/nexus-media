"""Rate limit decorators and context manager."""

from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable

from app.infrastructure.rate_limiter.backends import RateLimitEngine

_default_rate_limit_engine: RateLimitEngine | None = None


def _get_default_rate_limit_engine():
    global _default_rate_limit_engine
    if _default_rate_limit_engine is None:
        _default_rate_limit_engine = RateLimitEngine()
    return _default_rate_limit_engine


@contextmanager
def rate_limit(engine: RateLimitEngine, key: str, rate: str = "10/m", timeout: float | None = 60):
    """限流上下文管理器.

    :param engine: RateLimitEngine 实例
    :param key: 限流标识
    :param rate: 速率字符串
    :param timeout: 最大等待秒数
    :raises RateLimitExceeded: 限流超时
    """
    acquired = engine.acquire(key, rate, timeout=timeout)
    if not acquired:
        raise RuntimeError(f"Rate limit exceeded for {key}")
    try:
        yield
    finally:
        pass


def rate_limited(
    rate: str = "10/m",
    timeout: float | None = 60,
    key_func: Callable | None = None,
    engine: RateLimitEngine | None = None,
):
    """限流装饰器.

    :param rate: 速率字符串
    :param timeout: 最大等待秒数
    :param key_func: 从函数参数推导 key 的函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__module__}.{func.__name__}"
            _engine = engine or _get_default_rate_limit_engine()
            if _engine is None:
                return func(*args, **kwargs)
            with rate_limit(_engine, key, rate, timeout):
                return func(*args, **kwargs)

        return wrapper

    return decorator
