"""
数据库引擎初始化
提供延迟初始化的引擎和 session 工厂

设计原则：
- 不再使用 scoped_session 长期持有线程本地 session
- 通过普通 sessionmaker 创建短期 Session，由调用方显式管理生命周期
- 连接池仍由 SQLAlchemy Engine 管理，session 关闭后连接归还连接池
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.db.connection_scheduler import configure_connection_scheduler
from app.db.database_factory import DatabaseFactory

# =============================================================================
# 引擎与 Session 工厂（延迟初始化）
# =============================================================================

_Engine: Any | None = None
_SessionFactory: Any | None = None
_engine_lock = threading.Lock()

# 调度任务专用连接池：与 API 连接池隔离，避免二者相互耗尽（见 scheduler_engine_context）
_SchedulerEngine: Any | None = None
_SchedulerSessionFactory: Any | None = None

# 连接池上下文覆盖：调度任务执行期间设置，使得当前执行内的 DB 访问走调度专用引擎
_db_override: ContextVar[tuple[Any, Any] | None] = ContextVar("db_pool_override", default=None)


def _configure_connection_scheduler() -> None:
    """按配置装配全局连接调度器（每进程一次），作为所有引擎统一的连接准入闸门."""
    configure_connection_scheduler(
        capacity=DatabaseFactory._get_int_config("max_connections", DatabaseFactory.DEFAULT_MAX_CONNECTIONS),
        acquire_timeout=DatabaseFactory._get_int_config(
            "connection_acquire_timeout", DatabaseFactory.DEFAULT_CONNECTION_ACQUIRE_TIMEOUT
        ),
    )


def _init_engine():
    """延迟初始化引擎和 session 工厂（线程安全）"""
    global _Engine, _SessionFactory
    if _Engine is None:
        with _engine_lock:
            if _Engine is None:
                _configure_connection_scheduler()
                _Engine = DatabaseFactory.create_engine()
                _SessionFactory = sessionmaker(
                    bind=_Engine,
                    autoflush=False,
                    autocommit=False,
                    expire_on_commit=False,
                )


def _init_scheduler_engine():
    """延迟初始化调度任务专用引擎和 session 工厂（线程安全）"""
    global _SchedulerEngine, _SchedulerSessionFactory
    if _SchedulerEngine is None:
        with _engine_lock:
            if _SchedulerEngine is None:
                _SchedulerEngine = DatabaseFactory.create_engine(
                    pool_size=DatabaseFactory._get_int_config(
                        "scheduler_pool_size", DatabaseFactory.DEFAULT_SCHEDULER_POOL_SIZE
                    ),
                    max_overflow=DatabaseFactory._get_int_config(
                        "scheduler_max_overflow", DatabaseFactory.DEFAULT_SCHEDULER_MAX_OVERFLOW
                    ),
                    pool_timeout=DatabaseFactory._get_int_config(
                        "scheduler_pool_timeout", DatabaseFactory.DEFAULT_SCHEDULER_POOL_TIMEOUT
                    ),
                )
                _SchedulerSessionFactory = sessionmaker(
                    bind=_SchedulerEngine,
                    autoflush=False,
                    autocommit=False,
                    expire_on_commit=False,
                )


def get_engine() -> Engine:
    """获取数据库引擎（调度任务执行期间返回调度专用引擎）"""
    override = _db_override.get()
    if override is not None:
        return override[0]
    _init_engine()
    assert _Engine is not None
    return _Engine


def get_session_factory():
    """获取 session 工厂（调度任务执行期间返回调度专用工厂）"""
    override = _db_override.get()
    if override is not None:
        return override[1]
    _init_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def get_engine_override() -> Engine | None:
    """当前上下文覆盖的引擎（无覆盖时返回 None）"""
    override = _db_override.get()
    return override[0] if override is not None else None


def get_session_factory_override():
    """当前上下文覆盖的 session 工厂（无覆盖时返回 None）"""
    override = _db_override.get()
    return override[1] if override is not None else None


@contextmanager
def scheduler_engine_context() -> Iterator[None]:
    """调度任务执行上下文：本次执行内的 DB 访问使用调度专用连接池。

    基于 contextvars，仅影响当前执行上下文（含事件循环任务）；调度任务在独立线程执行，
    据此与 API 请求的连接池隔离，避免同时占满同一连接池导致 API 请求等待/超时。
    """
    _init_scheduler_engine()
    assert _SchedulerEngine is not None and _SchedulerSessionFactory is not None
    token = _db_override.set((_SchedulerEngine, _SchedulerSessionFactory))
    try:
        yield
    finally:
        _db_override.reset(token)


def new_session():
    """创建一个全新的 Session（调用方必须负责 close/remove）"""
    return get_session_factory()()
