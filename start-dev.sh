#!/bin/sh
# Nexus Media FastAPI 开发模式启动脚本
# 使用 Granian 单进程启动（带热重载）

FASTAPI_PORT=${FASTAPI_PORT:-3000}

echo "【FastAPI】启动 Nexus Media FastAPI 版本..."
echo "【FastAPI】监听端口：$FASTAPI_PORT"

CONFIG="${NEXUS_MEDIA_CONFIG:-./config/config.yaml}"
if [ -f "$CONFIG" ]; then
    echo "【FastAPI】配置文件：$CONFIG"
else
    echo "【FastAPI】配置文件不存在，使用 .env + 默认值运行"
fi

uv run granian \
    --interface asgi \
    --host "::" \
    --port "$FASTAPI_PORT" \
    --reload \
    --log \
    run:app
