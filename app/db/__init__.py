import os

from alembic.command import upgrade as alembic_upgrade
from alembic.config import Config as AlembicConfig

import log
from app.utils.path_utils import get_root_path
from config import Config

from .database_factory import DatabaseFactory
from .main_db import (
    Database,
    DbPersist,
    MainDb,
    SessionManager,
    get_engine,
    get_session_manager,
    remove_session,
)
from .media_db import MediaDb
from .sql_adapter import SQLAdapter, adapt_sql_for_engine


def init_db():
    """
    初始化数据库
    """
    log.console('开始初始化数据库...')
    MediaDb().init_db()
    SessionManager().create_all()
    log.console('数据库初始化完成')
    update_db()


def init_data():
    """
    初始化数据
    """
    log.console('开始初始化数据...')
    SessionManager().init_data()
    log.console('数据初始化完成')


def update_db():
    """
    更新数据库
    """
    script_location = os.path.normpath(os.path.join(get_root_path(), 'scripts'))
    log.console('开始更新数据库...')
    try:
        # 使用工厂获取数据库连接URL
        db_url = DatabaseFactory.get_alembic_url()

        # 对 URL 中的 % 进行转义，避免 Alembic ConfigParser 插值错误
        db_url_escaped = db_url.replace('%', '%%')

        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option('script_location', script_location)
        alembic_cfg.set_main_option('sqlalchemy.url', db_url_escaped)
        alembic_upgrade(alembic_cfg, 'head')
        log.console('数据库更新完成')
    except Exception as e:
        log.error(f'数据库更新失败: {str(e)}')
