#!/usr/bin/env python3
import os
import re

API_DIR = "web/frontend/apps/nas-tools/src/api/modules"

# 需要改为 POST 的路径模式
POST_PATHS = [
    "/api/brush/tasks",
    "/api/download/tasks",
    "/api/download/history",
    "/api/download/downloaders",
    "/api/filter/rules",
    "/api/media/detail",
    "/api/media/library/count",
    "/api/plugin/plugins",
    "/api/plugin/plugins/config",
    "/api/rss/movie/list",
    "/api/rss/tv/list",
    "/api/rss/history",
    "/api/userrss/tasks",
    "/api/scheduler/jobs",
    "/api/scheduler/logs",
    "/api/site/sites",
    "/api/site/sites/detail",
    "/api/site/sites/statistics",
    "/api/sync/paths",
    "/api/system/status",
    "/api/system/logs",
    "/api/words/words",
    "/api/rbac/codes",
]


def fix_file(path: str):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    original = content
    for p in POST_PATHS:
        pattern = rf"requestClient\.get(<[^>]+>)?(\('{re.escape(p)}')"

        def repl(m):
            return f"requestClient.post{m.group(1) or ''}{m.group(2)}"

        content = re.sub(pattern, repl, content)
    if content != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Fixed: {path}")


def main():
    for fname in os.listdir(API_DIR):
        if fname.endswith(".ts"):
            fix_file(os.path.join(API_DIR, fname))


if __name__ == "__main__":
    main()
