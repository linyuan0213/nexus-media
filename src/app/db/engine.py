"""
数据库引擎初始化
提供延迟初始化的引擎和 session 工厂

设计原则：
- 不再使用 scoped_session 长期持有线程本地 session
- 通过普通 sessionmaker 创建短期 Session，由调用方显式管理生命周期
- 连接池仍由 SQLAlchemy Engine 管理，session 关闭后连接归还连接池
"""

import threading
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.db.database_factory import DatabaseFactory

# =============================================================================
# 引擎与 Session 工厂（延迟初始化）
# =============================================================================

_Engine: Any | None = None
_SessionFactory: Any | None = None
_engine_lock = threading.Lock()


def _init_engine():
    """延迟初始化引擎和 session 工厂（线程安全）"""
    global _Engine, _SessionFactory
    if _Engine is None:
        with _engine_lock:
            if _Engine is None:
                _Engine = DatabaseFactory.create_engine()
                _SessionFactory = sessionmaker(
                    bind=_Engine,
                    autoflush=False,
                    autocommit=False,
                    expire_on_commit=False,
                )


def get_engine() -> Engine:
    """获取数据库引擎"""
    _init_engine()
    assert _Engine is not None
    return _Engine


def get_session_factory():
    """获取 session 工厂"""
    _init_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def new_session():
    """创建一个全新的 Session（调用方必须负责 close/remove）"""
    return get_session_factory()()
