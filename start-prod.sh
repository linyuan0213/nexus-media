#!/bin/sh
# Nexus Media 生产模式启动
PYTHONPATH="src:${PYTHONPATH}" uv run --no-sync python run.py "$@"
