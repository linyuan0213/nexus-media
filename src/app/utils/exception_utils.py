"""
异常处理工具

保留 exception_traceback 以兼容旧代码，
新增类型化异常转换和上下文日志方法。
"""

import traceback
from typing import TYPE_CHECKING, Never

import log

if TYPE_CHECKING:
    from app.core.exceptions import NexusError


class ExceptionUtils:
    @classmethod
    def exception_traceback(cls, e: BaseException, message: str = "") -> None:
        prefix = f"{message}: " if message else ""
        msg = f"{prefix}Exception: {str(e)}\nCallstack:\n{traceback.format_exc()}"
        log.error(msg)

    @classmethod
    def log_and_raise(
        cls,
        exc: BaseException,
        *,
        target: type["NexusError"] | None = None,
        message: str = "",
        code: str | None = None,
        details: dict | None = None,
    ) -> Never:
        """
        记录异常并抛出类型化异常。

        :param exc:      原始异常
        :param target:   要转换的目标 NexusError 子类
        :param message:  覆盖消息（留空则使用原始消息）
        :param code:     错误码
        :param details:  附加上下文
        """
        cls.exception_traceback(exc)
        if target is not None:
            raise target(message or str(exc), code=code, details=details) from exc
        raise exc

    @classmethod
    def safe_call(cls, func, *args, default=None, error_msg: str = "", **kwargs):
        """安全调用函数，失败时记录日志并返回 default"""
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            cls.exception_traceback(exc)
            return default
