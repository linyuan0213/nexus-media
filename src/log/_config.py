"""
日志配置读取与 handlers 构建。
"""

import json
import logging
import logging.handlers
import os
import sys
from typing import Any, TextIO

from app.core.settings import settings

__all__ = ["build_handlers"]

_JSON_FORMAT = os.environ.get("LOG_FORMAT", "").lower() == "json"


def _json_sink_factory(target: TextIO) -> Any:
    """返回一个 loguru sink callable，将记录序列化为 JSON 行并写入 target。"""

    def _sink(message: Any) -> None:
        record = message.record
        log_entry = {
            "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record["level"].name,
            "module": record.get("module", ""),
            "function": record.get("function", ""),
            "file": record.get("name") or "",
            "line": record.get("line", 0),
            "message": record["message"],
        }
        exc = record.get("exception")
        if exc:
            log_entry["exception"] = "{}: {}".format(
                exc.type.__name__ if exc.type else "",
                exc.value or "",
            )
        target.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
        target.flush()

    return _sink


_HUMAN_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level:8}| {file} : {module}.{function}:{line:4} | - {message}"
_HUMAN_FORMAT_COLOR = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} |<lvl>{level:8}</>| {file} : {module}.{function}:{line:4} | - <lvl>{message}</>"
)


def _is_json_enabled(log_cfg: dict[str, Any]) -> bool:
    return _JSON_FORMAT or log_cfg.get("format") == "json"


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
        except Exception:  # noqa: S110  # nosec B110
            # 日志发送失败时不应影响主流程
            pass


def build_handlers(module: str) -> list[dict[str, Any]]:
    """根据全局 Config 生成 loguru handlers 配置。"""
    log_cfg = settings.get("log") or {}
    logtype = log_cfg.get("type") or "console"
    use_json = _is_json_enabled(log_cfg)
    handlers: list[dict[str, Any]] = []

    if logtype == "server":
        logserver = (log_cfg.get("server") or "").split(":")
        if logserver and logserver[0]:
            logip = logserver[0]
            logport = int(logserver[1] or "514") if len(logserver) > 1 else 514
            handlers.append(
                {
                    "sink": _SyslogHandlerFactory(logip, logport),
                    "format": _HUMAN_FORMAT,
                    "colorize": False,
                }
            )
    elif logtype == "file":
        logpath = os.environ.get("NEXUS_MEDIA_LOG") or log_cfg.get("path") or ""
        if logpath:
            if not os.path.exists(logpath):
                os.makedirs(logpath)
            filepath = os.path.join(logpath, module + ".log")
            if use_json:
                handlers.append(
                    {
                        "sink": _json_sink_factory(open(filepath, "a")),
                        "format": "{message}",
                    }
                )
            else:
                handlers.append(
                    {
                        "sink": filepath,
                        "rotation": "5 MB",
                        "format": _HUMAN_FORMAT,
                        "colorize": False,
                        "retention": "5 days",
                    }
                )

    # 始终添加 stderr 终端输出
    if use_json:
        handlers.append(
            {
                "sink": _json_sink_factory(sys.stderr),
                "format": "{message}",
            }
        )
    else:
        handlers.append(
            {
                "sink": sys.stderr,
                "format": _HUMAN_FORMAT_COLOR,
                "colorize": True,
            }
        )
    return handlers
