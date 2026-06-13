"""测试全局配置与 Fixtures"""

import os

# 必须在导入任何项目模块之前设置
os.environ["NEXUS_MEDIA_CONFIG"] = os.path.join(os.path.dirname(__file__), "config_test.yaml")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def engine():
    """提供内存 SQLite 引擎"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine):
    """每个测试函数独立的数据库会话"""
    from app.db.models import Base

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def mock_config(monkeypatch):
    """提供隔离的 mock 配置"""

    class _MockConfig:
        def __init__(self):
            self._config = {
                "app": {"web_host": "0.0.0.0", "web_port": 3000, "rmt_tmdbkey": "test_key"},
                "database": {"type": "sqlite", "sqlite_path": ":memory:"},
            }

        def get_config(self, key, default=None):
            keys = key.split(".")
            val = self._config
            for k in keys:
                val = val.get(k, {})
            return val if val != {} else default

    return _MockConfig()
