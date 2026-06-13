"""通用工具函数"""

import functools

from tenacity import (
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity import (
    retry as _tenacity_retry,
)

import log


def retry(exception_to_check, tries: int = 3, delay: int | float = 3, backoff: int | float = 2, logger=None):
    """
    兼容旧 API 的重试装饰器，内部使用 tenacity。

    :param exception_to_check: 需要捕获的异常类型
    :param tries: 重试次数
    :param delay: 初始延迟时间（秒）
    :param backoff: 延迟倍数
    :param logger: 日志对象
    """

    def deco_retry(f):
        wrapped = _tenacity_retry(
            stop=stop_after_attempt(tries),
            wait=wait_exponential(multiplier=delay, exp_base=backoff, min=delay),
            retry=retry_if_exception_type(exception_to_check),
            reraise=True,
        )(f)

        @functools.wraps(f)
        def f_retry(*args, **kwargs):
            try:
                return wrapped(*args, **kwargs)
            except RetryError as e:
                original = e.last_attempt.exception()
                log.warn(f"{original}, 放弃重试")
                if original is not None:
                    raise original
                raise RuntimeError("Max retries exceeded")

        return f_retry

    return deco_retry
