# gunicorn FastAPI 配置文件
# 使用方式：gunicorn -c gunicorn.conf.py run:app

import os
import hashlib
import random
import ruamel.yaml
import shutil

config = os.environ.get('NASTOOL_CONFIG')
if not config:
    print("环境变量 NASTOOL_CONFIG 不存在")
    os._exit(-1)

if not os.path.exists(config):
    os.makedirs(os.path.dirname(config), exist_ok=True)
    cfg_tp_path = os.path.join('./config', "config.yaml")
    shutil.copy(cfg_tp_path, config)
    print("【Config】config.yaml 配置文件不存在，已将配置文件模板复制到配置目录...")

ssl_cert = ''
ssl_key = ''
with open(config, 'r') as f:
    try:
        yaml = ruamel.yaml.YAML()
        cf = yaml.load(f)
        ssl_cert = cf.get('app').get('ssl_cert') if cf.get('app') else None
        ssl_key = cf.get('app').get('ssl_key') if cf.get('app') else None
    except Exception as e:
        print("【Config】config.yaml 异常请删除重新配置...")

ROOT_PATH = os.path.dirname(os.path.abspath(config))
LOG_PATH = os.path.join(ROOT_PATH, 'logs')
if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

port = os.environ.get('NT_PORT') if os.environ.get('NT_PORT') else 3000

bind = f'[::]:{port}'
timeout = 60
daemon = False

# 使用 uvicorn worker（FastAPI）
worker_class = 'uvicorn.workers.UvicornWorker'
workers = int(os.environ.get('GUNICORN_WORKERS', 1))
threads = 4

loglevel = 'info'
pidfile = os.path.join(ROOT_PATH, "gunicorn.pid")

access_log_format = '%(t)s %(p)s %(h)s "%(r)s" %(s)s %(L)s %(b)s %(f)s" "%(a)s"'
accesslog = os.path.join(LOG_PATH, "gunicorn_access.log")
errorlog = '-'
graceful_timeout = 10
keyfile = ssl_key
certfile = ssl_cert
