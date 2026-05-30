import log

from .main_db import (
    Database,
    auto_commit,
    MainDb,
    SessionManager,
    get_engine,
    get_session_manager,
    remove_session,
)
from .sql_adapter import SQLAdapter, adapt_sql_for_engine


def init_db():
    """
    初始化数据库表结构
    数据库迁移（alembic upgrade head）由 Docker entrypoint 或部署脚本在启动前执行
    """
    log.console("开始初始化数据库表结构...")
    SessionManager().create_all()
    log.console("数据库表结构初始化完成")


def init_data():
    """
    初始化数据
    """
    log.console("开始初始化数据...")
    SessionManager().init_data()
    log.console("数据初始化完成")
