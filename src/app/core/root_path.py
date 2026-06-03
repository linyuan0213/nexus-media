"""项目根目录获取工具 — 零依赖，可被 settings.py 安全导入"""

import os
from pathlib import Path

__all__ = ["get_project_root"]

_root: Path | None = None


def get_project_root() -> Path:
    """获取项目根目录，优先级：PROJECT_ROOT 环境变量 > pyproject.toml 标记 > .git 标记，结果缓存。"""
    global _root
    if _root is not None:
        return _root
    if env_root := os.environ.get("PROJECT_ROOT"):
        _root = Path(env_root)
        return _root
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").is_file() or (parent / ".git").is_dir():
            _root = parent
            return _root
    raise RuntimeError("Cannot determine project root")


def get_script_path() -> str:
    """SQL 数据初始化脚本目录"""
    return str(get_project_root() / "src" / "app" / "db" / "data")
