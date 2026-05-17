#!/bin/sh
# NAS-Tools FastAPI 生产模式启动脚本
# 使用 gunicorn + uvicorn worker 启动

.venv/bin/gunicorn run:app -c gunicorn.conf.py
