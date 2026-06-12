#!/bin/sh
# 停止 Granian 服务器

PIDFILE="${1:-/data/granian.pid}"

if [ ! -f "$PIDFILE" ]; then
    PIDFILE="./data/granian.pid"
fi

if [ ! -f "$PIDFILE" ]; then
    # 兼容旧路径
    PIDFILE="./config/logs/granian.pid"
fi

if [ ! -f "$PIDFILE" ]; then
    PIDFILE="/config/logs/granian.pid"
fi

if [ ! -f "$PIDFILE" ]; then
    echo "未找到 PID 文件：$PIDFILE"
    exit 1
fi

for pid in $(cat "$PIDFILE"); do
    if kill -0 "$pid" 2>/dev/null; then
        echo "发送 TERM 信号到 Granian 进程 $pid ..."
        kill -TERM "$pid"
    else
        echo "进程 $pid 不存在"
    fi
done

rm -f "$PIDFILE"
