"""数据库备份 v2：原生 dump + Parquet 跨库快照 + TOML manifest."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import tomllib
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import tomli_w
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    Table,
    Time,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.types import LargeBinary

import log
from app.core.settings import settings
from app.db.database_factory import DatabaseFactory
from app.db.migrate import (
    _deserialize_value,
    _quote_identifier,
    _reset_postgresql_sequences,
    _sort_tables_topological,
    export_database,
    get_all_table_names,
    import_database,
)
from app.infrastructure.temp import temp_manager
from app.plugin_framework.private_pack import safe_extract
from app.schemas.system import BackupRestoreResultDTO
from version import APP_VERSION

FORMAT_VERSION = 2
MANIFEST_NAME = "manifest.toml"
NATIVE_DIR = "database/native"
PORTABLE_DIR = "database/portable"
_EXCLUDED_TABLES = {"alembic_version"}


def _is_internal_table(name: str) -> bool:
    """旧迁移/备份表不参与 portable 快照，目标库通常没有这些表."""
    return name in _EXCLUDED_TABLES or name.startswith("MIGRATION_") or "_BAK_" in name


_PLUGIN_EXCLUDES = {"*.bak-*", "*.tmp", "*.log", "__pycache__", "*.pyc"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_dialect(engine: Engine) -> str:
    return "sqlite" if DatabaseFactory.is_sqlite(engine) else engine.dialect.name


def _alembic_revision(engine: Engine) -> str:
    try:
        with engine.connect() as conn:
            value = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return str(value or "")
    except Exception:
        return ""


def _copy_plugin_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*_PLUGIN_EXCLUDES), dirs_exist_ok=True)


def _arrow_schema(table: Table) -> pa.Schema:
    fields: list[pa.Field] = []
    for column in table.columns:
        col_type = column.type
        if isinstance(col_type, Boolean):
            arrow_type = pa.bool_()
        elif isinstance(col_type, Integer):
            arrow_type = pa.int64()
        elif isinstance(col_type, Numeric):
            precision = getattr(col_type, "precision", None) or 38
            scale = getattr(col_type, "scale", None) or 0
            arrow_type = pa.decimal128(int(precision), int(scale)) if int(precision) <= 38 else pa.float64()
        elif isinstance(col_type, Float):
            arrow_type = pa.float64()
        elif isinstance(col_type, DateTime):
            arrow_type = pa.timestamp("us")
        elif isinstance(col_type, Date):
            arrow_type = pa.date32()
        elif isinstance(col_type, Time):
            arrow_type = pa.time64("us")
        elif isinstance(col_type, LargeBinary):
            arrow_type = pa.binary()
        else:
            arrow_type = pa.string()
        fields.append(pa.field(column.name, arrow_type, nullable=column.nullable))
    return pa.schema(fields)


def _arrow_value(value: Any, arrow_type: pa.DataType) -> Any:
    if value is None:
        return None
    if pa.types.is_string(arrow_type) and isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if pa.types.is_string(arrow_type) and not isinstance(value, str):
        if isinstance(value, (datetime, date, dt_time)):
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8", errors="replace")
        return str(value)
    if pa.types.is_binary(arrow_type) and isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    return value


def _table_rows(engine: Engine, table: Table, chunk_size: int = 1000) -> Iterator[list[dict[str, Any]]]:
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(table.select())
        columns = list(result.keys())
        while True:
            rows = result.fetchmany(chunk_size)
            if not rows:
                break
            yield [dict(zip(columns, row, strict=False)) for row in rows]


def _export_portable_table(engine: Engine, table: Table, target: Path) -> int:
    schema = _arrow_schema(table)
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(target, schema, compression="zstd")
    count = 0
    try:
        wrote = False
        for rows in _table_rows(engine, table):
            arrays = [
                pa.array([_arrow_value(row.get(field.name), field.type) for row in rows], type=field.type)
                for field in schema
            ]
            writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
            count += len(rows)
            wrote = True
        if not wrote:
            # 空表也写 schema，跨库恢复时可以明确知道列集合。
            arrays = [pa.array([], type=field.type) for field in schema]
            writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
    finally:
        writer.close()
    return count


def _table_names(engine: Engine) -> list[str]:
    return [name for name in get_all_table_names(engine) if not _is_internal_table(name)]


def _mysql_defaults_file(engine: Engine) -> str:
    url = engine.url
    fd, path = tempfile.mkstemp(prefix="nexus_mysqldump_")
    os.close(fd)
    os.chmod(path, 0o600)
    with open(path, "w", encoding="utf-8") as f:
        f.write("[client]\n")
        f.write(f"host={url.host or 'localhost'}\n")
        f.write(f"port={url.port or 3306}\n")
        f.write(f"user={url.username or ''}\n")
        f.write(f"password={url.password or ''}\n")
    return path


def _native_mysql(engine: Engine, target: Path) -> None:
    if not shutil.which("mysqldump"):
        raise RuntimeError("mysqldump 未安装，无法创建 MySQL 原生备份")
    defaults = _mysql_defaults_file(engine)
    try:
        cmd = [
            "mysqldump",
            f"--defaults-extra-file={defaults}",
            "--single-transaction",
            "--quick",
            "--routines",
            "--triggers",
            "--events",
            "--hex-blob",
            "--default-character-set=utf8mb4",
            "--no-tablespaces",
            "--skip-ssl",
            str(engine.url.database or "nexus_media"),
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdout is not None
        try:
            with gzip.open(target, "wb") as out:
                shutil.copyfileobj(proc.stdout, out)
            stderr = proc.stderr.read() if proc.stderr is not None else b""
            returncode = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
        if returncode != 0:
            raise RuntimeError(f"mysqldump 失败: {stderr.decode(errors='replace')[-500:]}")
    finally:
        os.unlink(defaults)


def _native_postgresql(engine: Engine, target: Path) -> None:
    if not shutil.which("pg_dump"):
        raise RuntimeError("pg_dump 未安装，无法创建 PostgreSQL 原生备份")
    url = engine.url
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    cmd = [
        "pg_dump",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-h",
        str(url.host or "localhost"),
        "-p",
        str(url.port or 5432),
        "-U",
        str(url.username or "postgres"),
        "-d",
        str(url.database or "nexus_media"),
        "-f",
        str(target),
    ]
    result = subprocess.run(cmd, env=env, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump 失败: {result.stderr.decode(errors='replace')[-500:]}")


def _native_sqlite(engine: Engine, target: Path) -> None:
    db_path = DatabaseFactory._get_config_value("sqlite_path") or str(Path(settings.data_path) / "user.db")
    with sqlite3.connect(db_path) as source, sqlite3.connect(target) as dst:
        source.backup(dst)


def _create_native(engine: Engine, target: Path) -> str:
    dialect = _source_dialect(engine)
    if dialect == "sqlite":
        _native_sqlite(engine, target)
    elif dialect == "mysql":
        _native_mysql(engine, target)
    elif dialect == "postgresql":
        _native_postgresql(engine, target)
    else:
        raise RuntimeError(f"不支持的原生备份数据库: {dialect}")
    return dialect


def create_backup(bk_path: str | None = None) -> str | None:
    """创建 v2 备份 zip；不生成 JSON 数据库导出."""
    data_path = Path(settings.data_path)
    backup_name = f"nexus_media_backup_{time.strftime('%Y-%m-%d_%H-%M-%S')}"
    root = Path(bk_path) / backup_name if bk_path else data_path / "backup_file" / backup_name
    root.mkdir(parents=True, exist_ok=True)
    engine = DatabaseFactory.create_engine(pool_size=1, max_overflow=0)
    try:
        dialect = _source_dialect(engine)
        native_dir = root / NATIVE_DIR
        native_dir.mkdir(parents=True, exist_ok=True)
        native_name = {"sqlite": "sqlite.db", "mysql": "mysql.sql.gz", "postgresql": "postgres.dump"}.get(dialect)
        if not native_name:
            raise RuntimeError(f"不支持的数据库类型: {dialect}")
        native_path = native_dir / native_name
        _create_native(engine, native_path)

        portable_dir = root / PORTABLE_DIR
        portable_dir.mkdir(parents=True, exist_ok=True)
        metadata = MetaData()
        metadata.reflect(bind=engine, only=_table_names(engine))
        table_info: dict[str, dict[str, Any]] = {}
        for table in metadata.sorted_tables:
            if _is_internal_table(table.name):
                continue
            filename = f"{table.name}.parquet"
            rows = _export_portable_table(engine, table, portable_dir / filename)
            table_info[table.name] = {
                "rows": rows,
                "columns": [column.name for column in table.columns],
            }

        config_file = data_path / "config.yaml"
        if config_file.exists():
            (root / "config").mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_file, root / "config" / "config.yaml")
        _copy_plugin_tree(data_path / "plugins", root / "plugins")
        _copy_plugin_tree(data_path / "plugins_data", root / "plugins_data")

        manifest = {
            "format_version": FORMAT_VERSION,
            "app_version": APP_VERSION,
            "source_dialect": dialect,
            "alembic_revision": _alembic_revision(engine),
            "created_at": _now(),
            "tables": table_info,
            "checksums": {
                str(path.relative_to(root)): _sha256(path)
                for path in root.rglob("*")
                if path.is_file() and path.name != MANIFEST_NAME
            },
        }
        with open(root / MANIFEST_NAME, "wb") as f:
            tomli_w.dump(manifest, f)
    finally:
        engine.dispose()

    zip_file = str(root) + ".zip"
    with zipfile.ZipFile(zip_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(root))
    shutil.rmtree(root, ignore_errors=True)
    return zip_file


def _read_manifest(temp_dir: Path) -> dict:
    manifest_path = temp_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise RuntimeError("不是 v2 备份：缺少 manifest.toml，旧版 JSON 备份不再支持")
    with open(manifest_path, "rb") as f:
        return tomllib.load(f)


def _copy_restored_files(temp_dir: Path, data_path: Path) -> None:
    config_src = temp_dir / "config" / "config.yaml"
    if config_src.exists():
        shutil.copy2(config_src, data_path / "config.yaml")
    for folder in ("plugins", "plugins_data"):
        src = temp_dir / folder
        if src.exists():
            _copy_plugin_tree(src, data_path / folder)


def _native_restore(engine: Engine, dialect: str, temp_dir: Path) -> None:
    native_dir = temp_dir / NATIVE_DIR
    if dialect == "sqlite":
        source = native_dir / "sqlite.db"
        if not source.exists():
            raise RuntimeError("备份缺少 sqlite.db")
        target = Path(DatabaseFactory._get_config_value("sqlite_path") or str(Path(settings.data_path) / "user.db"))
        engine.dispose()
        for suffix in ("-wal", "-shm"):
            try:
                os.remove(f"{target}{suffix}")
            except FileNotFoundError:
                pass
        shutil.copy2(source, target)
        return
    if dialect == "mysql":
        source = native_dir / "mysql.sql.gz"
        if not source.exists():
            raise RuntimeError("备份缺少 mysql.sql.gz")
        if not shutil.which("mysql"):
            raise RuntimeError("mysql 客户端未安装")
        defaults = _mysql_defaults_file(engine)
        try:
            engine.dispose()
            with gzip.open(source, "rb") as src:
                result = subprocess.run(
                    [
                        "mysql",
                        "--skip-ssl",
                        f"--defaults-extra-file={defaults}",
                        str(engine.url.database or "nexus_media"),
                    ],
                    stdin=cast(Any, src),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            if result.returncode != 0:
                raise RuntimeError(f"mysql 恢复失败: {result.stderr.decode(errors='replace')[-500:]}")
        finally:
            os.unlink(defaults)
        return
    if dialect == "postgresql":
        source = native_dir / "postgres.dump"
        if not source.exists():
            raise RuntimeError("备份缺少 postgres.dump")
        if not shutil.which("pg_restore"):
            raise RuntimeError("pg_restore 未安装")
        url = engine.url
        env = dict(os.environ)
        if url.password:
            env["PGPASSWORD"] = str(url.password)
        engine.dispose()
        result = subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "-h",
                str(url.host or "localhost"),
                "-p",
                str(url.port or 5432),
                "-U",
                str(url.username or "postgres"),
                "-d",
                str(url.database or "nexus_media"),
                str(source),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pg_restore 失败: {result.stderr.decode(errors='replace')[-500:]}")
        return
    raise RuntimeError(f"不支持的原生恢复数据库: {dialect}")


def _portable_restore(engine: Engine, temp_dir: Path, manifest: dict) -> None:
    info = manifest.get("tables") or {}
    table_names = [str(name) for name in info if not _is_internal_table(str(name))]
    existing = set(get_all_table_names(engine))
    missing = sorted(set(table_names) - existing)
    if missing:
        raise RuntimeError(f"目标数据库缺少表: {', '.join(missing[:8])}")

    metadata = MetaData()
    metadata.reflect(bind=engine, only=table_names)
    sorted_tables = _sort_tables_topological(engine, table_names)
    if not sorted_tables:
        return
    insert_tables = [metadata.tables[name] for name in sorted_tables]
    portable_dir = temp_dir / PORTABLE_DIR
    with engine.connect() as conn:
        dialect = _source_dialect(engine)
        if dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        elif dialect == "mysql":
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        # PRAGMA/SET 会触发 SQLAlchemy autobegin，先结束隐式事务再显式 begin。
        conn.commit()
        trans = conn.begin()
        try:
            for table in reversed(insert_tables):
                conn.execute(table.delete())
            for table in insert_tables:
                parquet_path = portable_dir / f"{table.name}.parquet"
                if not parquet_path.exists():
                    continue
                rows = pq.read_table(parquet_path).to_pylist()
                if rows:
                    converted = []
                    for row in rows:
                        item = {}
                        for column in table.columns:
                            value = row.get(column.name)
                            if value is not None and isinstance(column.type, JSON) and isinstance(value, str):
                                try:
                                    value = json.loads(value)
                                except ValueError:
                                    pass
                            item[column.name] = _deserialize_value(value, column.type) if value is not None else None
                        converted.append(item)
                    conn.execute(table.insert(), converted)
            trans.commit()
        except Exception:
            trans.rollback()
            raise
        finally:
            if dialect == "sqlite":
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            elif dialect == "mysql":
                conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
    _reset_postgresql_sequences(engine, table_names)
    with engine.connect() as conn:
        for table in insert_tables:
            actual = conn.execute(text(f"SELECT COUNT(*) FROM {_quote_identifier(engine, table.name)}")).scalar()
            expected = int((info.get(table.name) or {}).get("rows") or 0)
            if int(actual or 0) != expected:
                raise RuntimeError(f"恢复行数校验失败: {table.name} {actual} != {expected}")


def _restore_legacy_json(temp_dir: Path, data_path: Path) -> BackupRestoreResultDTO:
    """仅兼容旧版备份包；新备份永远不写 JSON."""
    json_backup = temp_dir / "user_db_export.json"
    sqlite_backup = temp_dir / "user.db"
    target_engine = DatabaseFactory.create_engine(pool_size=1, max_overflow=0)
    source_engine = None
    try:
        if json_backup.exists():
            with open(json_backup, encoding="utf-8") as f:
                migrate_data = json.load(f)
        elif sqlite_backup.exists():
            source_engine = create_engine(f"sqlite:///{sqlite_backup}?check_same_thread=False")
            migrate_data = export_database(source_engine)
        else:
            return BackupRestoreResultDTO(success=False, message="备份文件中未找到数据库文件")
        source_tables = {name for name in (migrate_data.get("tables") or {}) if not _is_internal_table(str(name))}
        missing = sorted(source_tables - set(get_all_table_names(target_engine)))
        if missing:
            return BackupRestoreResultDTO(
                success=False,
                message=f"目标数据库 schema 未就绪，缺少表：{'、'.join(missing[:8])}。请先执行 alembic upgrade head",
            )
        import_database(target_engine, migrate_data)
        config_src = temp_dir / "config.yaml"
        if config_src.exists():
            shutil.copy2(config_src, data_path / "config.yaml")
        for folder in ("plugins", "plugins_data"):
            src = temp_dir / folder
            if src.exists():
                _copy_plugin_tree(src, data_path / folder)
        return BackupRestoreResultDTO(success=True, message="旧版备份恢复成功，请重启后端服务以刷新数据库连接")
    finally:
        target_engine.dispose()
        if source_engine is not None:
            source_engine.dispose()


def restore_backup(filename: str) -> BackupRestoreResultDTO:
    """恢复 v2 备份；同库优先 native，跨库使用 Parquet."""
    if not filename:
        return BackupRestoreResultDTO(success=False, message="文件不存在")
    data_path = Path(settings.data_path)
    file_path = Path(temp_manager.get_temp_path(filename))
    temp_dir = tempfile.mkdtemp(prefix="restore_v2_")
    engine: Engine | None = None
    try:
        if not file_path.exists():
            return BackupRestoreResultDTO(success=False, message="备份文件不存在")
        safe_extract(str(file_path), temp_dir)
        manifest_path = Path(temp_dir) / MANIFEST_NAME
        if not manifest_path.exists():
            return _restore_legacy_json(Path(temp_dir), data_path)
        manifest = _read_manifest(Path(temp_dir))
        if int(manifest.get("format_version") or 0) != FORMAT_VERSION:
            return BackupRestoreResultDTO(success=False, message="不支持的备份格式版本")
        for relative, expected in (manifest.get("checksums") or {}).items():
            file = Path(temp_dir) / relative
            if not file.is_file() or _sha256(file) != str(expected):
                return BackupRestoreResultDTO(success=False, message=f"备份校验失败: {relative}")
        engine = DatabaseFactory.create_engine(pool_size=1, max_overflow=0)
        target_dialect = _source_dialect(engine)
        source_dialect = str(manifest.get("source_dialect") or "")
        native_dir = Path(temp_dir) / NATIVE_DIR
        native_exists = {
            "sqlite": (native_dir / "sqlite.db").exists(),
            "mysql": (native_dir / "mysql.sql.gz").exists(),
            "postgresql": (native_dir / "postgres.dump").exists(),
        }.get(source_dialect, False)
        if source_dialect == target_dialect and native_exists:
            _native_restore(engine, target_dialect, Path(temp_dir))
        else:
            _portable_restore(engine, Path(temp_dir), manifest)
        _copy_restored_files(Path(temp_dir), data_path)
        return BackupRestoreResultDTO(success=True, message="恢复成功，请重启后端服务以刷新数据库连接")
    except Exception as exc:
        log.error(f"[BackupV2]恢复失败: {exc}")
        return BackupRestoreResultDTO(success=False, message=str(exc))
    finally:
        if engine is not None:
            engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)
        if file_path.exists():
            file_path.unlink()
