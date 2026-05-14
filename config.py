"""
根目录 config.py - 向后兼容入口
所有实现已迁移到 app.core.config / app.utils.config_tools / app.utils.path_utils
"""

from app.core.config import Config  # noqa: F401
from app.core.constants import *  # noqa: F401,F403
