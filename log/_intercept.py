# -*- coding: utf-8 -*-
"""
拦截标准库 logging 到 loguru 的 Handler。
"""

import logging

from loguru import logger

__all__ = ["InterceptHandler"]


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 1
        while frame.f_code.co_filename == logging.__file__ or frame.f_code.co_filename == __file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
