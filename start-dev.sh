#!/bin/sh
# Nexus Media 开发模式启动（热重载）
PYTHONPATH="src:${PYTHONPATH}" uv run python run.py --dev
