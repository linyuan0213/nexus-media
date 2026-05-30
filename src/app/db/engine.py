"""
数据库引擎初始化
提供延迟初始化的引擎和 session 工厂
"""

import threading
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.database_factory import DatabaseFactory

# =============================================================================
# 引擎与 Session 工厂（延迟初始化）
# =============================================================================

_Engine: Any | None = None
_SessionFactory: Any | None = None
_ScopedSession: Any | None = None
_engine_lock = threading.Lock()


def _init_engine():
    """延迟初始化引擎和 session 工厂（线程安全）"""
    global _Engine, _SessionFactory, _ScopedSession
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
                _ScopedSession = scoped_session(_SessionFactory)


def get_engine() -> Engine:
    """获取数据库引擎"""
    _init_engine()
    assert _Engine is not None
    return _Engine


def get_scoped_session():
    """获取当前线程的 scoped_session"""
    _init_engine()
    return _ScopedSession
