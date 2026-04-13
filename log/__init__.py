# -*- coding: utf-8 -*-
"""
日志模块

提供基于 loguru 的日志记录、LogBuffer 代理以及便捷 API。
"""

# 抑制第三方库日志噪音
import logging

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('watchdog').setLevel(logging.INFO)

from ._buffer_proxy import LOG_BUFFER, LogBufferProxy, get_log_buffer
from ._intercept import InterceptHandler
from ._logger_manager import Logger, get_logger_instance
from ._api import debug, info, error, warn, console
from ._compat import LOG_QUEUE, LOG_INDEX

__all__ = [
    # API
    "debug",
    "info",
    "error",
    "warn",
    "console",
    # 核心类
    "Logger",
    "get_logger_instance",
    "InterceptHandler",
    # Buffer 相关
    "LOG_BUFFER",
    "LogBufferProxy",
    "get_log_buffer",
    # 兼容别名
    "LOG_QUEUE",
    "LOG_INDEX",
]
