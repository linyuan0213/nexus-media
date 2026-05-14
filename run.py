#!/usr/bin/env python3
"""
NAS-Tools 启动入口 — FastAPI
已移除 Flask 依赖，统一使用 FastAPI
"""

import os
import signal
import warnings
import uvicorn

from config_monitor import stop_config_monitor

warnings.filterwarnings("ignore")

import log
from api.main import app
from app.services.system_service import SystemLifecycleService
from config import Config


def signal_handler(num, stack):
    """信号处理 - 优雅退出"""
    log.warn("捕捉到退出信号：%s，开始退出..." % num)
    log.info("关闭配置文件监控...")
    stop_config_monitor()
    log.info("关闭服务...")
    SystemLifecycleService().stop_service()
    log.info("退出主进程...")
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_run_config():
    """获取运行配置"""
    _web_host = "::"
    _web_port = 3000
    _ssl_cert = None
    _ssl_key = None
    _debug = False

    app_conf = Config().get_config("app")
    if app_conf:
        if app_conf.get("web_host"):
            host_val = app_conf.get("web_host")
            if host_val:
                _web_host = host_val.replace("[", "").replace("]", "")
        web_port_val = app_conf.get("web_port")
        _web_port = int(web_port_val) if web_port_val and str(web_port_val).isdigit() else 3000
        _ssl_cert = app_conf.get("ssl_cert")
        _ssl_key = app_conf.get("ssl_key")
        _debug = True if app_conf.get("debug") else False

    return {"host": _web_host, "port": _web_port, "ssl_cert": _ssl_cert, "ssl_key": _ssl_key, "debug": _debug}


def main():
    """FastAPI 主入口"""

    log.console("NAS-Tools FastAPI 启动中...")
    log.console("当前版本号：v3.8.0")

    # 启动服务
    log.console("开始启动服务...")
    SystemLifecycleService().start_service()

    # 获取配置
    config = get_run_config()
    log.console(f"监听地址：{config['host']}:{config['port']}")

    ssl_kwargs = {}
    if config["ssl_cert"] and config["ssl_key"]:
        ssl_kwargs["ssl_certfile"] = config["ssl_cert"]
        ssl_kwargs["ssl_keyfile"] = config["ssl_key"]
        log.console("SSL 已启用")

    uvicorn.run(
        app,
        host=config["host"],
        port=config["port"],
        log_level="info" if config["debug"] else "warning",
        access_log=config["debug"],
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
