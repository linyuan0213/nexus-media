# gunicorn FastAPI 配置文件
# 使用方式: gunicorn -c gunicorn.conf.py run:app

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from app.core.settings import AppSettings

_settings = AppSettings()
_ssl_cert = _settings.app.ssl_cert or None
_ssl_key = _settings.app.ssl_key or None
_root = _settings.config_path or "."

# ---------- 网络绑定 ----------

port = os.environ.get("NEXUS_PORT", str(_settings.app.web_port))
bind = f"[::]:{port}"

# ---------- Worker 配置 ----------

worker_class = "uvicorn.workers.UvicornWorker"
workers = max(int(os.environ.get("GUNICORN_WORKERS", "1")), 1)
threads = 4
preload_app = False
worker_tmp_dir = os.environ.get("GUNICORN_TMP_DIR", "/tmp")
max_requests = 10000
max_requests_jitter = 1000

# ---------- 超时与连接 ----------

timeout = 300
graceful_timeout = 30
keepalive = 5

# ---------- 日志 ----------

_log_path = os.path.join(_root, "logs")
os.makedirs(_log_path, exist_ok=True)

loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(t)s %(p)s %(h)s "%(r)s" %(s)s %(L)s %(b)s %(f)s" "%(a)s"'
accesslog = os.path.join(_log_path, "gunicorn_access.log")
errorlog = "-"

# ---------- 进程管理 ----------

daemon = False
pidfile = os.path.join(_root, "gunicorn.pid")

# ---------- SSL ----------

if _ssl_key and _ssl_cert:
    keyfile = _ssl_key
    certfile = _ssl_cert
