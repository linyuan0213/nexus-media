#!/bin/sh
# 停止 gunicorn

if [ -z "$NASTOOL_CONFIG" ]; then
    echo "错误：NASTOOL_CONFIG 环境变量未设置"
    exit 1
fi

pid_dir=$(dirname "$NASTOOL_CONFIG")
pidfile="${pid_dir}/gunicorn.pid"

if [ ! -f "$pidfile" ]; then
    echo "未找到 PID 文件: $pidfile"
    exit 1
fi

for pid in $(cat "$pidfile"); do
    if kill -0 "$pid" 2>/dev/null; then
        echo "发送 TERM 信号到 gunicorn 进程 $pid ..."
        kill -TERM "$pid"
    else
        echo "进程 $pid 不存在"
    fi
done

rm -f "$pidfile"
