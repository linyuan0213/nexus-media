"""
Session 管理器
提供显式 session 生命周期管理

设计原则：
- 禁止使用 scoped_session 长期持有数据库连接
- 所有数据库操作必须通过 session_scope() / transaction_scope() 显式上下文
- 不再提供旧 MainDb 兼容 API（query/insert/delete/execute 等）
"""

import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.orm import Session

import log
from app.core.root_path import get_project_root
from app.core.settings import settings
from app.db.connection_scheduler import get_connection_scheduler
from app.db.engine import (
    get_engine,
    get_engine_override,
    get_session_factory,
    get_session_factory_override,
)
from app.db.models import Base
from app.db.sql_adapter import get_sql_adapter

# 显式事务上下文：transaction_scope() 内所有仓储的 session 复用它，保证真正的原子性
_tx_session: ContextVar[Session | None] = ContextVar("db_tx_session", default=None)


class SessionManager:
    """
    Session 管理器

    职责：
    1. 提供 session_scope() 上下文管理器，确保 session 自动提交/回滚/关闭
    2. 提供 transaction_scope() 显式事务上下文（供 Service 层组合多 Repository 操作）
    3. 提供 session() / remove() 给需要手动控制生命周期的场景
    4. 提供数据库初始化方法

    注意：
    - 不再提供 query/insert/delete/execute 等隐式 session API
    - Repository 层应通过 self.session() 显式获取 session
    - 不基于 scoped_session，每次 session_scope() 都会创建新的 Session
    """

    def __init__(self):
        self._engine = get_engine()
        self._factory = get_session_factory()

    def _resolve_factory(self):
        """调度任务上下文存在时使用其专用工厂，否则用本实例的工厂"""
        override = get_session_factory_override()
        return override if override is not None else self._factory

    @property
    def engine(self):
        override = get_engine_override()
        return override if override is not None else self._engine

    @property
    def session(self):
        """创建一个新的 Session。调用方必须负责 close。

        处于 transaction_scope() 内时返回共享 Session（由外层统一提交/关闭）。
        """
        shared = _tx_session.get()
        if shared is not None:
            return shared
        return self._resolve_factory()()

    def current_tx_session(self):
        """当前上下文共享的事务 Session（无则 None）"""
        return _tx_session.get()

    @contextmanager
    def session_scope(self):
        """
        事务范围的 session 上下文管理器。
        自动 commit/rollback/close，确保连接及时归还连接池。

        处于 transaction_scope() 内时复用共享 Session 且不提交/关闭（由外层统一处理），
        从而让多个仓储操作真正处于同一事务。
        非共享时先经全局连接调度器排队取得许可，close 后再归还：保证全进程在途连接
        数不超过预算、等待者按 FIFO 有序获取（issue #197）。
        """
        shared = _tx_session.get()
        if shared is not None:
            yield shared
            return
        with get_connection_scheduler().acquire():
            sess = self._resolve_factory()()
            try:
                yield sess
                sess.commit()
            except Exception:
                sess.rollback()
                raise
            finally:
                sess.close()

    @contextmanager
    def transaction_scope(self):
        """
        显式事务上下文管理器。
        供 Service 层组合多个 Repository 操作，保证原子性：
        期间仓储的 session/session_scope 均复用本 Session，仅在退出时统一提交。
        整个事务持有一个连接许可，退出（提交/回滚并关闭）后归还。
        """
        with get_connection_scheduler().acquire():
            sess = self._resolve_factory()()
            token = _tx_session.set(sess)
            try:
                yield sess
                sess.commit()
            except Exception:
                sess.rollback()
                raise
            finally:
                _tx_session.reset(token)
                sess.close()

    def remove(self):
        """
        兼容旧代码的 remove()。
        由于不再使用 scoped_session，此方法目前为空操作。
        """
        pass

    # -------------------------------------------------------------------------
    # 数据库初始化
    # -------------------------------------------------------------------------

    def create_all(self):
        """创建所有表"""
        assert self._engine is not None
        Base.metadata.create_all(self._engine)

    def init_db_version(self):
        """初始化数据库版本（清理 alembic_version）"""
        try:
            with self.session_scope() as db:
                db.execute(text("delete from alembic_version where 1"))
        except (OSError, ValueError) as err:
            log.warn(f"[SessionManager]初始化数据库版本失败: {err}")

    def init_data(self):
        """读取 SQL 脚本初始化数据"""
        config = settings.get()
        init_files = settings.get("app").get("init_files") or []
        config_dir = str(get_project_root() / "src" / "app" / "db" / "data")
        sql_files = [os.path.join(config_dir, f) for f in os.listdir(config_dir) if f.endswith(".sql")]
        config_flag = False
        for sql_file in sql_files:
            if os.path.basename(sql_file) not in init_files:
                config_flag = True
                with open(sql_file, encoding="utf-8") as f:
                    sql_list = f.read().split(";\n")
                    for sql in sql_list:
                        try:
                            adapted = get_sql_adapter().adapt_sql(sql)
                            if adapted and adapted.strip():
                                with self.session_scope() as db:
                                    db.execute(text(adapted))
                        except (OSError, ValueError) as err:
                            log.warn(f"[SessionManager]执行初始化 SQL 失败: {err}")
                init_files.append(os.path.basename(sql_file))
        if config_flag:
            config["app"]["init_files"] = init_files
            settings.save(config)


class Database:
    """
    数据库单例

    职责：管理数据库引擎，提供 SessionManager 访问
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._session_mgr = SessionManager()
        self._initialized = True

    @property
    def engine(self):
        return self._session_mgr.engine

    @property
    def session_manager(self):
        return self._session_mgr

    def create_all(self):
        self._session_mgr.create_all()

    def init_db_version(self):
        self._session_mgr.init_db_version()

    def init_data(self):
        self._session_mgr.init_data()


# ---------------------------------------------------------------------------
# 模块级快捷函数
# ---------------------------------------------------------------------------


def get_session_manager() -> SessionManager:
    """获取 SessionManager 实例"""
    return SessionManager()


def remove_session():
    """
    兼容旧代码的 remove_session()。
    由于不再使用 scoped_session，此方法目前为空操作，保留给未清理干净的调用点。
    """
    pass


def new_session():
    """创建一个全新的 Session（调用方必须负责 close）"""
    return get_session_factory()()
