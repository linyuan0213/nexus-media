import os
import threading
from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, scoped_session

from app.db.models import Base
from app.db.database_factory import DatabaseFactory
from app.db.sql_adapter import SQLAdapter
from app.utils import ExceptionUtils, PathUtils
from config import Config


# SQL 适配器实例
_sql_adapter = None

def get_sql_adapter():
    """获取 SQL 适配器实例"""
    global _sql_adapter
    if _sql_adapter is None:
        _sql_adapter = SQLAdapter(_Engine)
    return _sql_adapter

lock = threading.Lock()

# 使用工厂创建数据库引擎
# 自动从配置文件获取数据库类型和连接信息
_Engine = DatabaseFactory.create_engine()

_Session = scoped_session(sessionmaker(bind=_Engine,
                                       autoflush=False,  # 禁用自动flush以提高性能
                                       autocommit=False,
                                       expire_on_commit=False))

# 线程本地存储，用于会话管理
_thread_local = threading.local()


@contextmanager
def session_scope():
    """提供事务范围的session上下文管理器"""
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
        _Session.remove()


class MainDb:

    @property
    def session(self):
        return _Session()

    def init_db(self):
        with lock:
            Base.metadata.create_all(_Engine)
            self.init_db_version()

    def init_db_version(self):
        """
        初始化数据库版本
        """
        try:
            self.excute("delete from alembic_version where 1")
            self.commit()
        except Exception as err:
            print(str(err))

    def init_data(self):
        """
        读取config目录下的sql文件，并初始化到数据库，只处理一次
        """
        config = Config().get_config()
        init_files = Config().get_config("app").get("init_files") or []
        config_dir = Config().get_script_path()
        sql_files = PathUtils.get_dir_level1_files(in_path=config_dir, exts=".sql")
        config_flag = False
        for sql_file in sql_files:
            if os.path.basename(sql_file) not in init_files:
                config_flag = True
                with open(sql_file, "r", encoding="utf-8") as f:
                    sql_list = f.read().split(';\n')
                    for sql in sql_list:
                        try:
                            # 使用 SQL 适配器处理 SQL 语句
                            adapted_sql = get_sql_adapter().adapt_sql(sql)
                            if adapted_sql and adapted_sql.strip():
                                self.excute(adapted_sql)
                                self.commit()
                        except Exception as err:
                            print(str(err))
                init_files.append(os.path.basename(sql_file))
        if config_flag:
            config['app']['init_files'] = init_files
            Config().save_config(config)

    def insert(self, data):
        """
        插入数据
        """
        if isinstance(data, list):
            self.session.add_all(data)
        else:
            self.session.add(data)

    def bulk_insert(self, objects, batch_size=1000):
        """
        批量插入对象，分批处理以避免内存问题
        :param objects: 对象列表
        :param batch_size: 每批处理数量
        """
        if not objects:
            return
        
        for i in range(0, len(objects), batch_size):
            batch = objects[i:i + batch_size]
            self.session.bulk_save_objects(batch)
            self.session.flush()
        self.commit()

    def bulk_insert_mappings(self, model, mappings, batch_size=1000):
        """
        批量插入字典映射数据，比ORM对象插入更快
        :param model: 模型类
        :param mappings: 字典列表
        :param batch_size: 每批处理数量
        """
        if not mappings:
            return
        
        for i in range(0, len(mappings), batch_size):
            batch = mappings[i:i + batch_size]
            self.session.bulk_insert_mappings(model, batch)
            self.session.flush()
        self.commit()

    def query(self, *obj):
        """
        查询对象
        """
        # 对于 MySQL，提交当前事务以获取最新数据
        # 避免 REPEATABLE READ 隔离级别导致的缓存问题
        try:
            self.commit()
        except:
            pass
        return self.session.query(*obj)

    def excute(self, sql):
        """
        执行SQL语句
        """
        # 使用 SQL 适配器处理 SQL 语句
        adapted_sql = get_sql_adapter().adapt_sql(sql)
        if adapted_sql and adapted_sql.strip():
            self.session.execute(text(adapted_sql))

    def flush(self):
        """
        刷写
        """
        self.session.flush()

    def commit(self):
        """
        提交事务
        """
        self.session.commit()

    def rollback(self):
        """
        回滚事务
        """
        self.session.rollback()


class DbPersist(object):
    def __init__(self, db, max_retries=3, retry_delay=0.1):
        self.db = db
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def __call__(self, f):
        def persist(*args, **kwargs):
            last_error = None
            for attempt in range(self.max_retries):
                try:
                    ret = f(*args, **kwargs)
                    self.db.commit()
                    return ret if ret is not None else True
                except Exception as e:
                    last_error = e
                    self.db.rollback()
                    if attempt < self.max_retries - 1:
                        import time
                        time.sleep(self.retry_delay * (attempt + 1))  # 指数退避
                    else:
                        ExceptionUtils.exception_traceback(e)
                        return False
                finally:
                    # 确保 Session 关闭并重置
                    self.db.session.close()
                    _Session.remove()  # 清理 scoped_session
            return False
        return persist
