# -*- coding: utf-8 -*-
"""
日志配置读取与 handlers 构建。
"""

import logging
import logging.handlers
import os
import sys
from typing import Any, Dict, List

from config import Config

__all__ = ["build_handlers"]


class _SyslogHandlerFactory:
    """为 server 类型日志提供基于标准库 SysLogHandler 的可调用 sink。"""

    def __init__(self, ip: str, port: int = 514):
        self.handler = logging.handlers.SysLogHandler(address=(ip, port))
        formatter = logging.Formatter("%(message)s")
        self.handler.setFormatter(formatter)

    def __call__(self, message: str) -> None:
        try:
            record = logging.LogRecord(
                name="loguru",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=message.rstrip(),
                args=(),
                exc_info=None,
            )
            self.handler.emit(record)
        except Exception:
            # 日志发送失败时不应影响主流程
            pass


def build_handlers(module: str) -> List[Dict[str, Any]]:
    """根据全局 Config 生成 loguru handlers 配置。"""
    cfg = Config()
    log_cfg = cfg.get_config("log") or {}
    logtype = log_cfg.get("type") or "console"
    handlers: List[Dict[str, Any]] = []

    if logtype == "server":
        logserver = (log_cfg.get("server") or "").split(":")
        if logserver and logserver[0]:
            logip = logserver[0]
            logport = int(logserver[1] or "514") if len(logserver) > 1 else 514
            handlers.append(
                {
                    "sink": _SyslogHandlerFactory(logip, logport),
                    "format": (
                        "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level:8}| "
                        "{file} : {module}.{function}:{line:4} | - {message}"
                    ),
                    "colorize": False,
                }
            )
    elif logtype == "file":
        logpath = os.environ.get("NASTOOL_LOG") or log_cfg.get("path") or ""
        if logpath:
            if not os.path.exists(logpath):
                os.makedirs(logpath)
            handlers.append(
                {
                    "sink": os.path.join(logpath, module + ".log"),
                    "rotation": "5 MB",
                    "format": (
                        "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level:8}| "
                        "{file} : {module}.{function}:{line:4} | - {message}"
                    ),
                    "colorize": False,
                    "retention": "5 days",
                }
            )

    # 始终添加 stderr 终端输出
    handlers.append(
        {
            "sink": sys.stderr,
            "format": (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} |<lvl>{level:8}</>| "
                "{file} : {module}.{function}:{line:4} | - <lvl>{message}</>"
            ),
            "colorize": True,
        }
    )
    return handlers
