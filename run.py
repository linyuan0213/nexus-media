#!/usr/bin/env python3
"""Nexus Media 启动入口 — Granian 异步服务器

CLI 方式: granian run:app --interface asgi --host :: --port 3000
Python 方式: uv run python run.py
"""  # noqa: EXE001

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import log
from granian import Granian
from granian.constants import Interfaces
from granian.log import LogLevels

from app.core.settings import settings


def main():
    log.console("Nexus Media FastAPI 启动中...")
    log.console("当前版本号：v3.8.0")

    app_conf = settings.get("app") or {}
    host = app_conf.get("web_host", "::").replace("[", "").replace("]", "")
    port = int(app_conf.get("web_port", 3000))
    debug = bool(app_conf.get("debug"))

    log.console(f"监听地址：{host}:{port}")

    ssl_kwargs = {}
    if ssl_cert := app_conf.get("ssl_cert"):
        if ssl_key := app_conf.get("ssl_key"):
            ssl_kwargs["ssl_cert"] = ssl_cert
            ssl_kwargs["ssl_key"] = ssl_key
            log.console("SSL 已启用")

    server = Granian(
        "run:app",
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=1,
        log_enabled=True,
        log_level=LogLevels.info if debug else LogLevels.warning,
        log_access=debug,
        **ssl_kwargs,
    )
    server.serve()


if __name__ == "__main__":
    main()
