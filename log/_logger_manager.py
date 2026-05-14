"""
Logger 单例管理与 loguru 配置。
"""

import logging
import threading

from loguru import logger

from ._config import build_handlers
from ._intercept import InterceptHandler

__all__ = ["Logger", "get_logger_instance"]

# 使用 RLock 支持重入，减少死锁风险
_lock = threading.RLock()

# 模块级实例缓存
_instances: dict[str, "Logger"] = {}


class Logger:
    """基于 loguru 的按模块日志管理器。"""

    def __init__(self, module: str):
        self._module = module
        handlers = build_handlers(module)
        logger.configure(handlers=handlers)
        logging.basicConfig(handlers=[InterceptHandler()], level=0)
        self._log = logger

    @property
    def log(self):
        return self._log

    @classmethod
    def get_instance(cls, module: str) -> "Logger":
        if not module:
            module = "run"
        instance = _instances.get(module)
        if instance is not None:
            return instance
        with _lock:
            instance = _instances.get(module)
            if instance is not None:
                return instance
            instance = cls(module)
            _instances[module] = instance
        return instance


def get_logger_instance(module: str) -> Logger:
    return Logger.get_instance(module)
