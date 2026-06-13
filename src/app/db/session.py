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

import log
from sqlalchemy import text

from app.core.root_path import get_project_root
from app.core.settings import settings
from app.db.engine import get_engine, get_session_factory
from app.db.models import Base
from app.db.sql_adapter import get_sql_adapter


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

    @property
    def engine(self):
        return self._engine

    @property
    def session(self):
        """创建一个新的 Session。调用方必须负责 close。"""
        return self._factory()

    @contextmanager
    def session_scope(self):
        """
        事务范围的 session 上下文管理器。
        自动 commit/rollback/close，确保连接及时归还连接池。
        """
        sess = self._factory()
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
        供 Service 层组合多个 Repository 操作，保证原子性。
        """
        with self.session_scope() as session:
            yield session

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
        except Exception as err:
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
                        except Exception as err:
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
