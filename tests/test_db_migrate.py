"""
数据库迁移工具测试用例
验证 SQLite ↔ MySQL/PostgreSQL 的数据导出导入能力
"""
import json
import os
import tempfile
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ['FLASK_DEBUG'] = '1'

from app.db.migrate import (
    _serialize_value,
    export_database,
    export_to_file,
    get_all_table_names,
    get_table_data,
    import_database,
    import_from_file,
    migrate_database,
)
from app.db.models import CONFIGFILTERGROUP, CUSTOMWORDS, Base


class TestSerializeValue:
    """测试序列化函数"""

    def test_serialize_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert _serialize_value(dt) == "2024-01-15T10:30:00"

    def test_serialize_none(self):
        assert _serialize_value(None) is None

    def test_serialize_string(self):
        assert _serialize_value("hello") == "hello"

    def test_serialize_bytes(self):
        assert _serialize_value(b"test") == "test"


class TestExportImport:
    """测试导出导入核心逻辑"""

    @pytest.fixture
    def sqlite_engine(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        yield engine

    def test_get_all_table_names(self, sqlite_engine):
        tables = get_all_table_names(sqlite_engine)
        assert "CONFIG_FILTER_GROUP" in tables
        assert "CUSTOM_WORDS" in tables

    def test_get_table_data_empty(self, sqlite_engine):
        rows = get_table_data(sqlite_engine, "CONFIG_FILTER_GROUP")
        assert rows == []

    def test_export_import_roundtrip(self, sqlite_engine):
        # 插入测试数据
        Session = sessionmaker(bind=sqlite_engine)
        session = Session()
        group = CONFIGFILTERGROUP(
            ID=1,
            GROUP_NAME="测试组",
            IS_DEFAULT="N",
            NOTE="测试备注"
        )
        session.add(group)
        session.commit()
        session.close()

        # 导出
        data = export_database(sqlite_engine)
        assert "tables" in data
        assert "CONFIG_FILTER_GROUP" in data["tables"]
        assert len(data["tables"]["CONFIG_FILTER_GROUP"]) == 1
        assert data["tables"]["CONFIG_FILTER_GROUP"][0]["GROUP_NAME"] == "测试组"

        # 创建新的目标数据库
        target_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(target_engine)

        # 导入
        import_database(target_engine, data)

        # 验证
        Session2 = sessionmaker(bind=target_engine)
        session2 = Session2()
        result = session2.query(CONFIGFILTERGROUP).filter_by(ID=1).first()
        assert result is not None
        assert result.GROUP_NAME == "测试组"
        assert result.IS_DEFAULT == "N"
        session2.close()

    def test_export_import_with_exclude(self, sqlite_engine):
        Session = sessionmaker(bind=sqlite_engine)
        session = Session()
        session.add(CONFIGFILTERGROUP(ID=1, GROUP_NAME="G1", IS_DEFAULT="N"))
        session.add(CUSTOMWORDS(ID=1, GROUP_ID=1, REPLACED="a", REPLACE="b"))
        session.commit()
        session.close()

        data = export_database(sqlite_engine, exclude_tables=["CUSTOM_WORDS"])
        assert "CONFIG_FILTER_GROUP" in data["tables"]
        assert "CUSTOM_WORDS" not in data["tables"]

    def test_export_import_file_roundtrip(self, sqlite_engine):
        Session = sessionmaker(bind=sqlite_engine)
        session = Session()
        session.add(CONFIGFILTERGROUP(ID=2, GROUP_NAME="文件测试", IS_DEFAULT="Y"))
        session.commit()
        session.close()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            export_to_file(sqlite_engine, filepath)
            with open(filepath, encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded["tables"]["CONFIG_FILTER_GROUP"][0]["GROUP_NAME"] == "文件测试"

            target_engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(target_engine)
            import_from_file(target_engine, filepath)

            Session2 = sessionmaker(bind=target_engine)
            session2 = Session2()
            result = session2.query(CONFIGFILTERGROUP).filter_by(ID=2).first()
            assert result.GROUP_NAME == "文件测试"
            session2.close()
        finally:
            os.unlink(filepath)

    def test_migrate_database(self, sqlite_engine):
        Session = sessionmaker(bind=sqlite_engine)
        session = Session()
        session.add(CONFIGFILTERGROUP(ID=3, GROUP_NAME="迁移测试", IS_DEFAULT="N"))
        session.commit()
        session.close()

        target_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(target_engine)

        migrate_database(sqlite_engine, target_engine)

        Session2 = sessionmaker(bind=target_engine)
        session2 = Session2()
        result = session2.query(CONFIGFILTERGROUP).filter_by(ID=3).first()
        assert result.GROUP_NAME == "迁移测试"
        session2.close()

    def test_import_truncate_long_strings(self, sqlite_engine):
        """测试超长字符串在导入目标库时自动截断"""
        from sqlalchemy import Column, Integer as SAInteger, MetaData, String as SAString, Table

        from app.db.models import DOWNLOADHISTORY

        # 源库写入一条 ENCLOSURE 超长的记录
        Session = sessionmaker(bind=sqlite_engine)
        session = Session()
        long_enclosure = "magnet:?xt=urn:btih:" + "x" * 1000
        session.add(DOWNLOADHISTORY(
            ID=1, TITLE="测试", YEAR="2024", TYPE="电影",
            TMDBID="123", SE="", VOTE="8.0", POSTER="", OVERVIEW="",
            TORRENT="", ENCLOSURE=long_enclosure, SITE="", DESC=None,
            DOWNLOADER="", DOWNLOAD_ID="", SAVE_PATH="", DATE=""
        ))
        session.commit()
        session.close()

        data = export_database(sqlite_engine)

        # 目标库手工建表，将 ENCLOSURE 限制为 50，以验证截断逻辑
        target_engine = create_engine("sqlite:///:memory:")
        target_meta = MetaData()
        Table(
            'DOWNLOAD_HISTORY', target_meta,
            Column('ID', SAInteger, primary_key=True),
            Column('TITLE', SAString(255)),
            Column('YEAR', SAString(255)),
            Column('TYPE', SAString(255)),
            Column('TMDBID', SAString(255)),
            Column('SE', SAString(255)),
            Column('VOTE', SAString(255)),
            Column('POSTER', SAString(255)),
            Column('OVERVIEW', SAString(255)),
            Column('TORRENT', SAString(255)),
            Column('ENCLOSURE', SAString(50)),
            Column('SITE', SAString(255)),
            Column('DESC', SAString(255)),
            Column('DOWNLOADER', SAString(255)),
            Column('DOWNLOAD_ID', SAString(255)),
            Column('SAVE_PATH', SAString(512)),
            Column('DATE', SAString(20)),
        )
        target_meta.create_all(target_engine)

        import_database(target_engine, data, clear_before_import=False)

        Session2 = sessionmaker(bind=target_engine)
        session2 = Session2()
        result = session2.execute(
            text("SELECT ENCLOSURE FROM DOWNLOAD_HISTORY WHERE ID = 1")
        ).fetchone()
        assert result is not None
        assert len(result[0]) <= 50
        session2.close()


class TestCrossDialectMock:
    """模拟跨方言迁移场景"""

    def test_mysql_limit_in_get_table_data(self):
        # 使用 sqlite 引擎模拟，只要语法不报错即可
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        rows = get_table_data(engine, "CONFIG_FILTER_GROUP", limit=10)
        assert rows == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
