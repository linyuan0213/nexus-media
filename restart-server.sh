#!/bin/sh
# 优雅重启 Granian（SIGUSR1 信号）

if [ -z "$NEXUS_MEDIA_CONFIG" ]; then
    echo "错误：NEXUS_MEDIA_CONFIG 环境变量未设置"
    exit 1
fi

pid_dir=$(dirname "$NEXUS_MEDIA_CONFIG")
pidfile="${pid_dir}/granian.pid"

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
