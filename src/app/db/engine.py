"""
数据库引擎初始化
提供延迟初始化的引擎和 session 工厂
"""

import threading
from typing import Any

from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.database_factory import DatabaseFactory
from app.db.sql_adapter import SQLAdapter

# =============================================================================
# SQL 适配器（延迟初始化避免循环导入）
# =============================================================================

_sql_adapter = None
_sql_adapter_lock = threading.Lock()


def get_sql_adapter():
    """获取 SQL 适配器实例 - 线程安全"""
    global _sql_adapter
    if _sql_adapter is None:
        with _sql_adapter_lock:
            if _sql_adapter is None:
                _sql_adapter = SQLAdapter(get_engine())
    return _sql_adapter


# =============================================================================
# 引擎与 Session 工厂（延迟初始化）
# =============================================================================

_Engine: Any | None = None
_SessionFactory: Any | None = None
_ScopedSession: Any | None = None


def _init_engine():
    """延迟初始化引擎和 session 工厂"""
    global _Engine, _SessionFactory, _ScopedSession
    if _Engine is None:
        _Engine = DatabaseFactory.create_engine()
        _SessionFactory = sessionmaker(
            bind=_Engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        _ScopedSession = scoped_session(_SessionFactory)


def get_engine():
    """获取数据库引擎"""
    _init_engine()
    return _Engine
