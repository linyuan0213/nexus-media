"""备份 v2 格式测试（SQLite 原生 + Parquet，不含 JSON）."""

import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from app.services.system import backup_v2


def _make_db(path):
    engine = create_engine(f"sqlite:///{path}")
    metadata = MetaData()
    table = Table("DEMO", metadata, Column("ID", Integer, primary_key=True), Column("NAME", String(20)))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(table.insert(), [{"ID": 1, "NAME": "demo"}])
    return engine


def test_create_backup_contains_native_parquet_and_no_json(tmp_path):
    source = tmp_path / "source.db"
    engine = _make_db(source)
    with (
        patch.object(backup_v2, "settings", SimpleNamespace(data_path=str(tmp_path))),
        patch.object(backup_v2.DatabaseFactory, "create_engine", return_value=engine),
        patch.object(backup_v2.DatabaseFactory, "_get_config_value", return_value=str(source)),
    ):
        zip_path = backup_v2.create_backup(bk_path=str(tmp_path))

    assert zip_path is not None
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "manifest.toml" in names
    assert "database/native/sqlite.db" in names
    assert "database/portable/DEMO.parquet" in names
    assert not any(name.endswith(".json") for name in names)


def test_restore_v2_sqlite_native(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    engine = _make_db(source)
    with (
        patch.object(backup_v2, "settings", SimpleNamespace(data_path=str(tmp_path))),
        patch.object(backup_v2.DatabaseFactory, "create_engine", return_value=engine),
        patch.object(backup_v2.DatabaseFactory, "_get_config_value", return_value=str(source)),
    ):
        zip_path = backup_v2.create_backup(bk_path=str(tmp_path))

    target_engine = _make_db(target)
    with target_engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM DEMO")
    with (
        patch.object(backup_v2, "settings", SimpleNamespace(data_path=str(tmp_path))),
        patch.object(backup_v2.DatabaseFactory, "create_engine", return_value=target_engine),
        patch.object(backup_v2.DatabaseFactory, "_get_config_value", return_value=str(target)),
        patch.object(backup_v2.temp_manager, "get_temp_path", return_value=zip_path),
    ):
        result = backup_v2.restore_backup("backup.zip")

    assert result.success, result.message
    with target_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT NAME FROM DEMO WHERE ID=1").scalar() == "demo"


def test_cross_dialect_uses_portable_parquet(tmp_path):
    import zipfile

    import tomli_w

    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    engine = _make_db(source)
    with (
        patch.object(backup_v2, "settings", SimpleNamespace(data_path=str(tmp_path))),
        patch.object(backup_v2.DatabaseFactory, "create_engine", return_value=engine),
        patch.object(backup_v2.DatabaseFactory, "_get_config_value", return_value=str(source)),
    ):
        zip_path = backup_v2.create_backup(bk_path=str(tmp_path))

    # 模拟跨库备份：manifest 标记为 mysql，但保留 portable Parquet。
    assert zip_path is not None
    rewritten = tmp_path / "cross.zip"
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(rewritten, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "manifest.toml":
                manifest = backup_v2.tomllib.loads(data.decode())
                manifest["source_dialect"] = "mysql"
                data = tomli_w.dumps(manifest).encode()
            dst.writestr(item, data)

    target_engine = _make_db(target)
    with target_engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM DEMO")
    with (
        patch.object(backup_v2, "settings", SimpleNamespace(data_path=str(tmp_path))),
        patch.object(backup_v2.DatabaseFactory, "create_engine", return_value=target_engine),
        patch.object(backup_v2.DatabaseFactory, "_get_config_value", return_value=str(target)),
        patch.object(backup_v2.temp_manager, "get_temp_path", return_value=str(rewritten)),
    ):
        result = backup_v2.restore_backup("cross.zip")

    assert result.success, result.message
    with target_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT NAME FROM DEMO WHERE ID=1").scalar() == "demo"
