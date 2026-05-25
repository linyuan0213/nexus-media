"""数据库工厂单元测试"""

import pytest

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

        inspector = inspect(engine)
        assert inspector.get_table_names() == []
