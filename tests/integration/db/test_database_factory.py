"""数据库工厂单元测试"""

import pytest
from sqlalchemy import text

from app.db.database_factory import DatabaseFactory


class TestDatabaseFactory:
    def test_sqlite_url(self):
        url = DatabaseFactory.get_database_url(
            db_type="sqlite",
            db_path="/tmp/test.db",
        )
        assert url.startswith("sqlite:///")
        assert "/tmp/test.db" in url
        assert "check_same_thread=False" in url

    def test_sqlite_url_in_memory(self):
        url = DatabaseFactory.get_database_url(
            db_type="sqlite",
            db_path=":memory:",
        )
        assert "sqlite:///:memory:" in url

    def test_mysql_url(self):
        url = DatabaseFactory.get_database_url(
            db_type="mysql",
            host="localhost",
            port=3306,
            username="user",
            password="pass",
            database="testdb",
        )
        assert url.startswith("mysql+pymysql://")
        assert "user:pass@localhost:3306/testdb" in url

    def test_postgresql_url(self):
        url = DatabaseFactory.get_database_url(
            db_type="postgresql",
            host="localhost",
            port=5432,
            username="user",
            password="pass",
            database="testdb",
        )
        assert url.startswith("postgresql+psycopg2://")
        assert "user:pass@localhost:5432/testdb" in url

    def test_special_chars_password(self):
        url = DatabaseFactory.get_database_url(
            db_type="mysql",
            host="localhost",
            port=3306,
            username="user",
            password="p@ss:w#rd",
            database="testdb",
        )
        assert "p%40ss%3Aw%23rd" in url

    def test_invalid_db_type(self):
        with pytest.raises(ValueError, match="不支持的数据库类型"):
            DatabaseFactory.get_database_url(db_type="oracle")

    def test_sqlite_missing_path(self):
        with pytest.raises(ValueError, match="db_path"):
            DatabaseFactory.get_database_url(db_type="sqlite")

    def test_create_sqlite_engine(self):
        engine = DatabaseFactory.create_engine(db_type="sqlite", db_path=":memory:")
        from sqlalchemy import inspect

        try:
            inspector = inspect(engine)
            assert inspector.get_table_names() == []
        finally:
            engine.dispose()

    def test_sqlite_pragmas_applied(self, tmp_path):
        db_path = tmp_path / "test_pragmas.db"
        engine = DatabaseFactory.create_engine(db_type="sqlite", db_path=str(db_path))
        try:
            with engine.connect() as conn:
                journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
                assert journal_mode and journal_mode.lower() == "wal"
                assert conn.execute(text("PRAGMA synchronous;")).scalar() == 1
                assert conn.execute(text("PRAGMA busy_timeout;")).scalar() == 30000
                assert conn.execute(text("PRAGMA wal_autocheckpoint;")).scalar() == 1000
        finally:
            engine.dispose()

    def test_sqlite_memory_uses_static_pool(self):
        engine = DatabaseFactory.create_engine(db_type="sqlite", db_path=":memory:")
        try:
            from sqlalchemy.pool import StaticPool

            assert isinstance(engine.pool, StaticPool)
        finally:
            engine.dispose()

    def test_sqlite_file_uses_null_pool(self, tmp_path):
        db_path = tmp_path / "test_null_pool.db"
        engine = DatabaseFactory.create_engine(db_type="sqlite", db_path=str(db_path))
        try:
            from sqlalchemy.pool import NullPool

            assert isinstance(engine.pool, NullPool)
        finally:
            engine.dispose()
