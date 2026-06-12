#!/bin/sh
# 优雅重启 Granian（SIGUSR1 信号）

pidfile="${1:-/data/granian.pid}"

if [ ! -f "$pidfile" ]; then
    pidfile="./data/granian.pid"
fi

if [ ! -f "$pidfile" ]; then
    # 兼容旧路径
    pidfile="./config/logs/granian.pid"
fi

if [ ! -f "$pidfile" ]; then
    pidfile="/config/logs/granian.pid"
fi

if [ ! -f "$pidfile" ]; then
    echo "未找到 PID 文件: $pidfile"
    exit 1
fi

for pid in $(cat "$pidfile"); do
    if kill -0 "$pid" 2>/dev/null; then
        echo "发送 USR1 信号到 Granian 进程 $pid ..."
        kill -USR1 "$pid"
    else
        echo "进程 $pid 不存在"
    fi
done
