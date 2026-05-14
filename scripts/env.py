from logging.config import fileConfig

from alembic import context

from app.db.database_factory import DatabaseFactory
from app.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_url():
    """
    获取数据库连接URL
    优先使用配置文件中的URL，如果没有则使用工厂生成
    """
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return DatabaseFactory.get_alembic_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()

    # 根据数据库类型配置不同的迁移选项
    dialect_opts = {"paramstyle": "named"}

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts=dialect_opts,
        render_as_batch=True,  # 支持SQLite的批量操作
        compare_type=True,  # 比较列类型
        compare_server_default=True,  # 比较默认值
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # 使用工厂创建引擎
    connectable = DatabaseFactory.create_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # 支持SQLite的批量操作
            compare_type=True,  # 比较列类型
            compare_server_default=True,  # 比较默认值
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
