#!/bin/sh
# Nexus Media FastAPI 生产模式启动脚本
# 使用 gunicorn + uvicorn worker 启动
# NEXUS_MEDIA_CONFIG 可选，未设置时自动发现

CONFIG="${NEXUS_MEDIA_CONFIG:-./config/config.yaml}"
if [ -f "$CONFIG" ]; then
    echo "【FastAPI】配置文件：$CONFIG"
else
    echo "【FastAPI】配置文件不存在，使用 .env + 默认值运行"
fi

.venv/bin/gunicorn run:app -c gunicorn.conf.py
