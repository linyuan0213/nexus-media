# coding: utf-8
"""
数据库工厂模块测试用例
测试 SQLite、MySQL、PostgreSQL 三种数据库的支持
"""
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

# 设置测试环境变量
os.environ['FLASK_DEBUG'] = '1'

# 测试前需要导入的模块
from app.db.database_factory import DatabaseFactory, DatabaseDialect
from app.db.sql_adapter import SQLAdapter, adapt_sql_for_engine
from sqlalchemy import create_engine, text, Engine
from sqlalchemy.orm import sessionmaker


class TestDatabaseFactory:
    """测试数据库工厂类"""
    
    def test_get_database_url_sqlite(self):
        """测试获取 SQLite 连接URL"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            url = DatabaseFactory.get_database_url(
                db_type='sqlite',
                db_path=db_path
            )
            assert 'sqlite:///' in url
            assert db_path in url
            assert 'check_same_thread=False' in url
        finally:
            os.unlink(db_path)
    
    def test_get_database_url_mysql(self):
        """测试获取 MySQL 连接URL"""
        url = DatabaseFactory.get_database_url(
            db_type='mysql',
            host='localhost',
            port=3306,
            username='test_user',
            password='test_pass@123',
            database='test_db'
        )
        assert 'mysql+pymysql://' in url
        assert 'test_user' in url
        assert 'test_pass%40123' in url  # URL编码后的@
        assert 'localhost:3306' in url
        assert 'test_db' in url
    
    def test_get_database_url_postgresql(self):
        """测试获取 PostgreSQL 连接URL"""
        url = DatabaseFactory.get_database_url(
            db_type='postgresql',
            host='localhost',
            port=5432,
            username='postgres',
            password='test_pass@123',
            database='test_db'
        )
        assert 'postgresql+psycopg2://' in url
        assert 'postgres' in url
        assert 'localhost:5432' in url
        assert 'test_db' in url
    
    def test_create_engine_sqlite(self):
        """测试创建 SQLite 引擎"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            engine = DatabaseFactory.create_engine(
                db_type='sqlite',
                db_path=db_path,
                is_media_db=False
            )
            assert isinstance(engine, Engine)
            assert DatabaseFactory.is_sqlite(engine)
            
            # 测试连接
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            os.unlink(db_path)
    
    def test_is_sqlite(self):
        """测试检测 SQLite 数据库"""
        engine = create_engine("sqlite:///:memory:")
        assert DatabaseFactory.is_sqlite(engine)
        assert not DatabaseFactory.is_mysql(engine)
        assert not DatabaseFactory.is_postgresql(engine)
    
    def test_is_mysql(self):
        """测试检测 MySQL 数据库"""
        # 使用 mock 引擎测试
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'mysql+pymysql'
        assert DatabaseFactory.is_mysql(mock_engine)
        assert not DatabaseFactory.is_sqlite(mock_engine)
    
    def test_is_postgresql(self):
        """测试检测 PostgreSQL 数据库"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'postgresql+psycopg2'
        assert DatabaseFactory.is_postgresql(mock_engine)
        assert not DatabaseFactory.is_sqlite(mock_engine)


class TestSQLAdapter:
    """测试 SQL 适配器类"""
    
    def test_adapt_insert_or_ignore_sqlite(self):
        """测试适配 INSERT OR IGNORE - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        adapter = SQLAdapter(engine)
        
        sql = 'INSERT OR IGNORE INTO "CONFIG_FILTER_GROUP" ("ID","GROUP_NAME") VALUES (1,"test")'
        result = adapter.adapt_sql(sql)
        # SQLite 保持原样
        assert 'INSERT OR IGNORE INTO' in result
    
    def test_adapt_insert_or_ignore_mysql(self):
        """测试适配 INSERT OR IGNORE - MySQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'mysql+pymysql'
        adapter = SQLAdapter(mock_engine)
        
        sql = 'INSERT OR IGNORE INTO "CONFIG_FILTER_GROUP" ("ID","GROUP_NAME") VALUES (1,"test")'
        result = adapter.adapt_sql(sql)
        # MySQL 转换为 INSERT IGNORE
        assert 'INSERT IGNORE INTO' in result
        assert 'OR IGNORE' not in result
    
    def test_adapt_insert_or_ignore_postgresql(self):
        """测试适配 INSERT OR IGNORE - PostgreSQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'postgresql+psycopg2'
        adapter = SQLAdapter(mock_engine)
        
        sql = 'INSERT OR IGNORE INTO "CONFIG_FILTER_GROUP" ("ID","GROUP_NAME") VALUES (1,"test")'
        result = adapter.adapt_sql(sql)
        # PostgreSQL 添加 ON CONFLICT DO NOTHING
        assert 'INSERT INTO' in result
        assert 'ON CONFLICT DO NOTHING' in result
    
    def test_adapt_delete_where_sqlite(self):
        """测试适配 DELETE WHERE 1 - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        adapter = SQLAdapter(engine)
        
        sql = "DELETE FROM alembic_version WHERE 1"
        result = adapter.adapt_sql(sql)
        assert "WHERE 1" in result
    
    def test_adapt_delete_where_postgresql(self):
        """测试适配 DELETE WHERE 1 - PostgreSQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'postgresql+psycopg2'
        adapter = SQLAdapter(mock_engine)
        
        sql = "DELETE FROM alembic_version WHERE 1"
        result = adapter.adapt_sql(sql)
        assert "WHERE TRUE" in result
        assert "WHERE 1" not in result
    
    def test_get_limit_clause_sqlite(self):
        """测试获取 LIMIT 子句 - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        adapter = SQLAdapter(engine)
        
        result = adapter.get_limit_clause(10, 5)
        assert result == "LIMIT 10 OFFSET 5"
    
    def test_get_limit_clause_mysql(self):
        """测试获取 LIMIT 子句 - MySQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'mysql+pymysql'
        adapter = SQLAdapter(mock_engine)
        
        result = adapter.get_limit_clause(10, 5)
        assert result == "LIMIT 5, 10"
    
    def test_get_current_timestamp_sqlite(self):
        """测试获取当前时间戳函数 - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        adapter = SQLAdapter(engine)
        
        result = adapter.get_current_timestamp()
        assert result == "datetime('now')"
    
    def test_get_current_timestamp_postgresql(self):
        """测试获取当前时间戳函数 - PostgreSQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'postgresql+psycopg2'
        adapter = SQLAdapter(mock_engine)
        
        result = adapter.get_current_timestamp()
        assert result == "CURRENT_TIMESTAMP"
    
    def test_get_date_format_sqlite(self):
        """测试获取日期格式化表达式 - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        adapter = SQLAdapter(engine)
        
        result = adapter.get_date_format("date_column", "%Y-%m-%d")
        assert result == "strftime('%Y-%m-%d', date_column)"
    
    def test_get_date_format_mysql(self):
        """测试获取日期格式化表达式 - MySQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'mysql+pymysql'
        adapter = SQLAdapter(mock_engine)
        
        result = adapter.get_date_format("date_column", "%Y-%m-%d")
        assert result == "DATE_FORMAT(date_column, '%Y-%m-%d')"
    
    def test_get_date_format_postgresql(self):
        """测试获取日期格式化表达式 - PostgreSQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'postgresql+psycopg2'
        adapter = SQLAdapter(mock_engine)
        
        result = adapter.get_date_format("date_column", "%Y-%m-%d")
        assert result == "TO_CHAR(date_column, 'YYYY-MM-DD')"


class TestDatabaseDialect:
    """测试数据库方言类"""
    
    def test_get_random_function_sqlite(self):
        """测试获取随机函数 - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        dialect = DatabaseDialect(engine)
        
        result = dialect.get_random_function()
        assert result == "RANDOM()"
    
    def test_get_random_function_mysql(self):
        """测试获取随机函数 - MySQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'mysql+pymysql'
        dialect = DatabaseDialect(mock_engine)
        
        result = dialect.get_random_function()
        assert result == "RAND()"
    
    def test_get_concat_function_sqlite(self):
        """测试获取字符串连接函数 - SQLite"""
        engine = create_engine("sqlite:///:memory:")
        dialect = DatabaseDialect(engine)
        
        result = dialect.get_concat_function("col1", "col2", "col3")
        assert result == "col1 || col2 || col3"
    
    def test_get_concat_function_mysql(self):
        """测试获取字符串连接函数 - MySQL"""
        mock_engine = MagicMock()
        mock_engine.url.drivername = 'mysql+pymysql'
        dialect = DatabaseDialect(mock_engine)
        
        result = dialect.get_concat_function("col1", "col2", "col3")
        assert result == "CONCAT(col1, col2, col3)"


class TestDatabaseIntegration:
    """测试数据库集成"""
    
    def test_sqlite_crud_operations(self):
        """测试 SQLite CRUD 操作"""
        from app.db.models import Base, CONFIGFILTERGROUP
        
        # 创建内存数据库
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # 创建记录
            group = CONFIGFILTERGROUP(
                ID=1,
                GROUP_NAME="测试组",
                IS_DEFAULT="N",
                NOTE="测试备注"
            )
            session.add(group)
            session.commit()
            
            # 读取记录
            result = session.query(CONFIGFILTERGROUP).filter_by(ID=1).first()
            assert result is not None
            assert result.GROUP_NAME == "测试组"
            
            # 更新记录
            result.GROUP_NAME = "更新后的测试组"
            session.commit()
            
            updated = session.query(CONFIGFILTERGROUP).filter_by(ID=1).first()
            assert updated.GROUP_NAME == "更新后的测试组"
            
            # 删除记录
            session.delete(updated)
            session.commit()
            
            deleted = session.query(CONFIGFILTERGROUP).filter_by(ID=1).first()
            assert deleted is None
        finally:
            session.close()


def test_global_adapt_sql_function():
    """测试全局适配函数"""
    sql = 'INSERT OR IGNORE INTO "TEST" ("ID") VALUES (1)'
    # 使用 SQLite 引擎进行测试
    engine = create_engine("sqlite:///:memory:")
    result = adapt_sql_for_engine(sql, engine)
    assert 'INSERT' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
