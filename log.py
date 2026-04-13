# -*- coding: utf-8 -*-
"""
日志模块入口（向后兼容）

本文件保留在项目根目录，使项目中大量 `import log` 的代码无需修改即可正常工作。
实际逻辑已迁移到 log 包中。
"""

from log import *  # noqa: F401, F403
