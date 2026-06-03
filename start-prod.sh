#!/bin/sh
# Nexus Media FastAPI 生产模式启动脚本
# 使用 Granian 原生多 worker 启动

WORKERS=${GRANIAN_WORKERS:-1}
PORT=${NEXUS_PORT:-3000}

CONFIG="${NEXUS_MEDIA_CONFIG:-./config/config.yaml}"
if [ -f "$CONFIG" ]; then
    echo "【FastAPI】配置文件：$CONFIG"
else
    echo "【FastAPI】配置文件不存在，使用 .env + 默认值运行"
fi

uv run granian \
    --interface asgi \
    --host "::" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log \
    --log-level warning \
    --no-access-log \
    run:app
