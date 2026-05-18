#!/bin/sh
# Nexus Media FastAPI 开发模式启动脚本
# 使用 uvicorn 单进程启动（带热重载）

# 检查环境变量
if [ -z "$NEXUS_MEDIA_CONFIG" ]; then
    echo "错误：NEXUS_MEDIA_CONFIG 环境变量未设置"
    echo "请先设置：export NEXUS_MEDIA_CONFIG=/path/to/config.yaml"
    exit 1
fi

# 默认端口
export FASTAPI_PORT=${FASTAPI_PORT:-3000}

echo "【FastAPI】启动 Nexus Media FastAPI 版本..."
echo "【FastAPI】配置文件：$NEXUS_MEDIA_CONFIG"
echo "【FastAPI】监听端口：$FASTAPI_PORT"

# 使用 uv run 启动（自动使用项目虚拟环境）
uv run uvicorn run:app \
    --host "::" \
    --port "$FASTAPI_PORT" \
    --log-level info \
    --access-log \
    --reload
