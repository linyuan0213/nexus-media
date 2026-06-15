"""
对外暴露的便捷日志 API（debug / info / error / warn / console）。
"""

import inspect

from ._buffer_proxy import LOG_BUFFER
from ._logger_manager import get_logger_instance

__all__ = ["debug", "info", "error", "warn", "console"]


def _caller_depth() -> int:
    """计算调用者相对于当前文件的深度，用于 loguru.opt(depth=...)。"""
    frame, depth = inspect.currentframe(), 0
    while frame and (depth == 0 or frame.f_code.co_filename == __file__):
        frame = frame.f_back
        depth += 1
    return depth


def debug(text: str, module: str | None = None) -> None:
    """记录 DEBUG 级别日志."""
    get_logger_instance(module or "nexus-media").log.opt(depth=_caller_depth()).debug(text)


def info(text: str, module: str | None = None) -> None:
    """记录 INFO 级别日志."""
    get_logger_instance(module or "nexus-media").log.opt(depth=_caller_depth()).info(text)


def error(text: str, module: str | None = None) -> None:
    """记录 ERROR 级别日志."""
    get_logger_instance(module or "nexus-media").log.opt(depth=_caller_depth()).error(text)


def warn(text: str, module: str | None = None) -> None:
    """记录 WARNING 级别日志."""
    get_logger_instance(module or "nexus-media").log.opt(depth=_caller_depth()).warning(text)


def console(text: str) -> None:
    LOG_BUFFER.append("INFO", text)
    print(text)
