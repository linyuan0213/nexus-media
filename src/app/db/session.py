"""
Session 管理器
提供 scoped_session 生命周期管理和兼容 API
"""

import os
import threading
from contextlib import contextmanager

from sqlalchemy import text

from app.core.root_path import get_project_root
from app.core.settings import settings
from app.db.engine import _init_engine, get_engine, get_scoped_session
from app.db.sql_adapter import get_sql_adapter
from app.db.models import Base


class SessionManager:
    """
    Session 管理器

    职责：
    1. 管理 scoped_session 生命周期（线程本地存储）
    2. 提供 session_scope() 上下文管理器确保自动提交/回滚/关闭
    3. 兼容旧 MainDb API（query/insert/commit/delete/flush/execute）
    4. 提供 bulk_insert / bulk_insert_mappings 批量操作
    5. 支持显式事务控制（transaction_scope）

    线程安全：scoped_session 保证同一线程内返回同一个 session 实例
    Session 清理：请求结束后必须调用 remove() 清理线程本地存储
    """

    _tx_local = threading.local()

    def __init__(self):
        _init_engine()
        self._engine = get_engine()
        self._scoped = get_scoped_session()

    def _session(self):
        assert self._scoped is not None
        return self._scoped()

    @property
    def _tx_depth(self) -> int:
        return getattr(self._tx_local, "depth", 0)

    @_tx_depth.setter
    def _tx_depth(self, value: int):
        self._tx_local.depth = value

    @property
    def in_transaction(self) -> bool:
        """当前线程是否处于显式事务中"""
        return self._tx_depth > 0

    @contextmanager
    def transaction_scope(self):
        """
        显式事务上下文管理器（支持嵌套）
        """
        self._tx_depth += 1
        depth = self._tx_depth
        try:
            yield
            if depth == 1:
                self.commit()
        except Exception:
            if depth == 1:
                self.rollback()
            raise
        finally:
            self._tx_depth = depth - 1

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
                                self.execute(adapted)
                                self.commit()
                        except Exception as err:
                            print(str(err))
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


# 向后兼容别名
MainDb = SessionManager


# ---------------------------------------------------------------------------
# 模块级快捷函数
# ---------------------------------------------------------------------------


def get_session_manager() -> SessionManager:
    """获取 SessionManager 实例"""
    return SessionManager()


def remove_session():
    """移除当前线程的 session（应在请求/任务结束时调用）"""
    scoped = get_scoped_session()
    if scoped:
        try:
            scoped().close()
        except Exception:
            pass
        finally:
            try:
                scoped.remove()
            except Exception:
                pass


def get_db_session():
    """获取当前线程的数据库 session"""
    scoped = get_scoped_session()
    assert scoped is not None
    return scoped()
