import os
import threading
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.database_factory import DatabaseFactory
from app.db.models import Base
from app.db.sql_adapter import SQLAdapter
from app.utils import ExceptionUtils, PathUtils
from app.utils.path_utils import get_script_path
from app.core.settings import settings

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


# =============================================================================
# SessionManager - Session 生命周期管理
# =============================================================================


class SessionManager:
    """
    Session 管理器

    职责：
    1. 管理 scoped_session 生命周期（线程本地存储）
    2. 提供 session_scope() 上下文管理器确保自动提交/回滚/关闭
    3. 兼容旧 MainDb API（query/insert/commit/delete/flush/execute）
    4. 提供 bulk_insert / bulk_insert_mappings 批量操作

    线程安全：scoped_session 保证同一线程内返回同一个 session 实例
    Session 清理：请求结束后必须调用 remove() 清理线程本地存储
    """

    def __init__(self):
        _init_engine()
        self._engine = _Engine
        self._scoped = _ScopedSession

    def _session(self):
        assert self._scoped is not None
        return self._scoped()

    @property
    def engine(self):
        return self._engine

    @property
    def session(self):
        """获取当前线程的 session（scoped_session）"""
        return self._session()

    @contextmanager
    def session_scope(self):
        """
        事务范围的 session 上下文管理器

        使用模式：
            with session_scope() as session:
                session.add(obj)
                # 自动 commit
            # 异常时自动 rollback，最终自动 close + remove
        """
        sess = self._session()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()
            if self._scoped:
                self._scoped.remove()

    def remove(self):
        """移除当前线程的 session（应在请求结束时调用）"""
        if self._scoped:
            self._scoped.remove()

    # -------------------------------------------------------------------------
    # 兼容旧 MainDb API
    # -------------------------------------------------------------------------

    def query(self, *entities):
        """创建查询（返回 Query 对象，不自动 commit）"""
        return self._session().query(*entities)

    def insert(self, data):
        """插入对象（单条或列表，不自动 commit）"""
        if isinstance(data, list):
            self._session().add_all(data)
        else:
            self._session().add(data)

    def delete(self, obj):
        """删除对象（不自动 commit）"""
        self._session().delete(obj)

    def commit(self):
        """提交当前线程事务"""
        self._session().commit()

    def rollback(self):
        """回滚当前线程事务"""
        self._session().rollback()

    def flush(self):
        """刷写当前线程 session"""
        self._session().flush()

    def execute(self, sql):
        """执行 SQL（保持旧拼写兼容，内部使用 SQL 适配器）"""
        adapted = get_sql_adapter().adapt_sql(sql)
        if adapted and adapted.strip():
            self._session().execute(text(adapted))

    def bulk_insert(self, objects, batch_size=1000):
        """批量插入 ORM 对象"""
        if not objects:
            return
        sess = self._session()
        for i in range(0, len(objects), batch_size):
            batch = objects[i : i + batch_size]
            sess.bulk_save_objects(batch)
            sess.flush()
        sess.commit()

    def bulk_insert_mappings(self, model, mappings, batch_size=1000):
        """批量插入字典映射（比 ORM 对象插入更快）"""
        if not mappings:
            return
        sess = self._session()
        for i in range(0, len(mappings), batch_size):
            batch = mappings[i : i + batch_size]
            sess.bulk_insert_mappings(model, batch)
            sess.flush()
        sess.commit()

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
            self.execute("delete from alembic_version where 1")
            self.commit()
        except Exception as err:
            print(str(err))

    def init_data(self):
        """读取 SQL 脚本初始化数据"""
        config = settings.get()
        init_files = settings.get("app").get("init_files") or []
        config_dir = get_script_path()
        sql_files = PathUtils.get_dir_level1_files(in_path=config_dir, exts=".sql")
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
                                self.execute(adapted)
                                self.commit()
                        except Exception as err:
                            print(str(err))
                init_files.append(os.path.basename(sql_file))
        if config_flag:
            config["app"]["init_files"] = init_files
            settings.save(config)


# =============================================================================
# Database - 数据库单例（引擎管理）
# =============================================================================


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


# =============================================================================
# 向后兼容别名
# =============================================================================

MainDb = SessionManager


# =============================================================================
# DbPersist - 自动重试持久化装饰器
# =============================================================================


class DbPersist:
    """
    持久化装饰器 - 自动重试的 commit/rollback

    重要变更：不再关闭 session（scoped_session 同线程共享，
    由请求级别 remove_session() 统一清理）
    """

    def __init__(self, db=None, max_retries=3, retry_delay=0.1):
        self.db = db
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def __call__(self, f):
        def persist(*args, **kwargs):
            for attempt in range(self.max_retries):
                try:
                    ret = f(*args, **kwargs)
                    if self.db:
                        self.db.commit()
                    return ret if ret is not None else True
                except Exception as e:
                    if self.db:
                        self.db.rollback()
                    if attempt < self.max_retries - 1:
                        import time

                        time.sleep(self.retry_delay * (attempt + 1))
                    else:
                        ExceptionUtils.exception_traceback(e)
                        return False
            return False

        return persist


# =============================================================================
# 模块级快捷函数
# =============================================================================


def remove_session():
    """移除当前线程的 session（应在请求/任务结束时调用）"""
    _init_engine()
    if _ScopedSession:
        _ScopedSession.remove()


def get_session_manager():
    """获取 SessionManager 实例"""
    return SessionManager()


def get_db_session():
    """获取当前线程的数据库 session"""
    _init_engine()
    assert _ScopedSession is not None
    return _ScopedSession()
