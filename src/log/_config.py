"""日志配置读取与 handlers 构建。"""

import json
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


def build_handlers(module: str) -> list[dict[str, Any]]:
    """根据全局 Config 生成 loguru handlers 配置。"""
    log_cfg = settings.get("log") or {}
    logtype = log_cfg.get("type") or "console"
    use_json = _is_json_enabled(log_cfg)
    handlers: list[dict[str, Any]] = []

    if logtype == "file":
        logpath = log_cfg.get("path") or ""
        if not logpath:
            logpath = os.path.join(settings.data_path, "logs")
            os.makedirs(logpath, exist_ok=True)
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
