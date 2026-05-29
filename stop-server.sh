#!/bin/sh
# 停止 gunicorn

PIDFILE="${1:-./config/gunicorn.pid}"

if [ ! -f "$PIDFILE" ]; then
    PIDFILE="/config/gunicorn.pid"
fi

if [ ! -f "$PIDFILE" ]; then
    echo "未找到 PID 文件：$PIDFILE"
    exit 1
fi

for pid in $(cat "$PIDFILE"); do
    if kill -0 "$pid" 2>/dev/null; then
        echo "发送 TERM 信号到 gunicorn 进程 $pid ..."
        kill -TERM "$pid"
    else
        echo "进程 $pid 不存在"
    fi
done

rm -f "$PIDFILE"
