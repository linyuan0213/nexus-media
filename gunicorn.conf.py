# gunicorn FastAPI 配置文件
# 使用方式: gunicorn -c gunicorn.conf.py run:app

import os
import shutil
import tempfile

import ruamel.yaml

# ---------- 配置初始化 ----------

config = os.environ.get("NASTOOL_CONFIG")
if not config:
    print("环境变量 NASTOOL_CONFIG 不存在")
    os._exit(-1)

if not os.path.exists(config):
    os.makedirs(os.path.dirname(config), exist_ok=True)
    cfg_tp_path = os.path.join("./config", "config.yaml")
    if os.path.exists(cfg_tp_path):
        shutil.copy(cfg_tp_path, config)
        print("【Config】config.yaml 配置文件不存在，已将配置文件模板复制到配置目录...")
    else:
        print(f"【Config】配置文件模板不存在: {cfg_tp_path}")

ssl_cert: str | None = None
ssl_key: str | None = None

with open(config, encoding="utf-8") as f:
    try:
        yaml = ruamel.yaml.YAML()
        cf = yaml.load(f)
        app_cfg = cf.get("app") if cf else {}
        if app_cfg:
            ssl_cert = app_cfg.get("ssl_cert")
            ssl_key = app_cfg.get("ssl_key")
    except Exception:
        print("【Config】config.yaml 异常请删除重新配置...")

ROOT_PATH = os.path.dirname(os.path.abspath(config))
LOG_PATH = os.path.join(ROOT_PATH, "logs")
if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

# ---------- 网络绑定 ----------

port = os.environ.get("NT_PORT", "3000")
if not port:
    port = "3000"

bind = f"[::]:{port}"

# ---------- Worker 配置 ----------

# 使用 uvicorn worker（FastAPI 异步支持）
worker_class = "uvicorn.workers.UvicornWorker"

# 默认 1 个 worker（项目有全局单例/内存缓存，多进程需额外验证）
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
workers = max(workers, 1)

# 每个 worker 的线程数（对 UvicornWorker 无实际作用，仅保留兼容）
threads = 4

# 预加载应用（减少 worker 启动时间，但内存占用增加）
preload_app = False

# worker 临时目录（Docker 中避免 /tmp 写满）
worker_tmp_dir = os.environ.get("GUNICORN_TMP_DIR", tempfile.gettempdir())

# 最大请求数后自动重启 worker（防止内存泄漏）
max_requests = 10000
max_requests_jitter = 1000

# ---------- 超时与连接 ----------

# 超时时间增加以支持 LLM 识别等长耗时操作
timeout = 300
graceful_timeout = 30
keepalive = 5

# ---------- 日志 ----------

loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(t)s %(p)s %(h)s "%(r)s" %(s)s %(L)s %(b)s %(f)s" "%(a)s"'
accesslog = os.path.join(LOG_PATH, "gunicorn_access.log")
errorlog = "-"

# ---------- 进程管理 ----------

daemon = False
pidfile = os.path.join(ROOT_PATH, "gunicorn.pid")

# ---------- SSL ----------

if ssl_key and ssl_cert:
    keyfile = ssl_key
    certfile = ssl_cert
