"""DB 连接池配置与调度任务独立连接池测试."""

import threading
from unittest.mock import MagicMock

from app.db import engine as db_engine
from app.db.connection_budget import ConnectionBudget, load_connection_budget
from app.db.database_factory import DatabaseFactory
from app.services import sync_engine as se


def test_default_pool_budget_leaves_room_for_other_clients():
    """默认连接预算不应独占 PostgreSQL 官方默认的 100 个槽位.

    回归防护：曾用 20+20 与 10+10 合计 60，占 PG 默认 max_connections=100 的六成，
    同实例再跑 odoo 等客户端就会把槽位挤爆，overflow 新建连接被 FATAL 拒绝。
    """
    main_max = DatabaseFactory.DEFAULT_POOL_SIZE + DatabaseFactory.DEFAULT_MAX_OVERFLOW
    scheduler_max = DatabaseFactory.DEFAULT_SCHEDULER_POOL_SIZE + DatabaseFactory.DEFAULT_SCHEDULER_MAX_OVERFLOW
    # 总上限不超过 PG 官方默认 100 的 30%
    assert main_max + scheduler_max <= 30
    # 常驻连接（pool_size 之和）不超过总上限的一半，空闲时不会长期占住槽位
    assert DatabaseFactory.DEFAULT_POOL_SIZE + DatabaseFactory.DEFAULT_SCHEDULER_POOL_SIZE <= 15


def test_is_connection_slot_exhausted_detects_pg_fatal():
    exc = Exception(
        '(psycopg2.OperationalError) connection to server at "postgres" (172.21.0.4), port 5432 failed: '
        "FATAL:  remaining connection slots are reserved for roles with the SUPERUSER attribute"
    )
    assert DatabaseFactory.is_connection_slot_exhausted(exc) is True


def test_is_connection_slot_exhausted_ignores_unrelated_errors():
    assert DatabaseFactory.is_connection_slot_exhausted(None) is False
    assert DatabaseFactory.is_connection_slot_exhausted(Exception("duplicate key value")) is False


def test_describe_pool_budget_mentions_total(monkeypatch):
    DatabaseFactory.reset_connection_budget()
    monkeypatch.setenv("DATABASE__POOL_SIZE", "5")
    monkeypatch.setenv("DATABASE__MAX_OVERFLOW", "5")
    monkeypatch.setenv("DATABASE__SCHEDULER_POOL_SIZE", "2")
    monkeypatch.setenv("DATABASE__SCHEDULER_MAX_OVERFLOW", "2")
    text = DatabaseFactory.describe_pool_budget()
    assert "主池 5+5=10 条" in text
    assert "调度池 2+2=4 条" in text


def test_get_int_config_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE__POOL_SIZE", "33")
    assert DatabaseFactory._get_int_config("pool_size", 20) == 33


def test_get_int_config_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("DATABASE__POOL_SIZE", raising=False)
    fake_settings = MagicMock()
    fake_settings.get.return_value = {"database": {}}
    monkeypatch.setattr("app.db.database_factory.settings", fake_settings)
    assert DatabaseFactory._get_int_config("pool_size", 20) == 20


def test_create_engine_applies_pool_env(monkeypatch):
    DatabaseFactory.reset_connection_budget()
    monkeypatch.setenv("DATABASE__POOL_SIZE", "33")
    monkeypatch.setenv("DATABASE__MAX_OVERFLOW", "7")
    monkeypatch.setenv("DATABASE__POOL_TIMEOUT", "9")
    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr("app.db.database_factory.create_engine", fake_create_engine)
    monkeypatch.setattr(DatabaseFactory, "_get_config_db_type", staticmethod(lambda: "postgresql"))
    monkeypatch.setattr(DatabaseFactory, "_ensure_database_exists", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(DatabaseFactory, "get_database_url", staticmethod(lambda *a, **k: "postgresql://x"))

    DatabaseFactory.create_engine()

    assert captured["pool_size"] == 33
    assert captured["max_overflow"] == 7
    assert captured["pool_timeout"] == 9
    # LIFO 让空闲连接自然过期，池不会长期驻留满 pool_size 条槽位
    assert captured["pool_use_lifo"] is True


def test_scheduler_engine_context_overrides_and_resets(monkeypatch):
    fake_engine = MagicMock()
    fake_factory = MagicMock(return_value="SESSION")
    monkeypatch.setattr(db_engine, "_SchedulerEngine", fake_engine)
    monkeypatch.setattr(db_engine, "_SchedulerSessionFactory", fake_factory)

    assert db_engine.get_engine_override() is None
    with db_engine.scheduler_engine_context():
        assert db_engine.get_engine() is fake_engine
        assert db_engine.get_session_factory() is fake_factory
    assert db_engine.get_engine_override() is None


def test_session_manager_uses_scheduler_factory(monkeypatch):
    from app.db.session import SessionManager

    fake_sess = MagicMock()
    fake_factory = MagicMock(return_value=fake_sess)
    monkeypatch.setattr(db_engine, "_SchedulerEngine", MagicMock())
    monkeypatch.setattr(db_engine, "_SchedulerSessionFactory", fake_factory)

    mgr = SessionManager.__new__(SessionManager)
    mgr._engine = MagicMock()
    mgr._factory = MagicMock()

    with db_engine.scheduler_engine_context():
        with mgr.session_scope() as session:
            assert session is fake_sess

    mgr._factory.assert_not_called()


def test_sync_reports_slot_exhausted_once_per_window(monkeypatch):
    """连接槽位耗尽按时间窗口汇总，不能每个文件刷一条."""
    engine = se.SyncEngine.__new__(se.SyncEngine)
    engine._slot_exhausted_lock = threading.Lock()
    engine._slot_exhausted_last = 0.0
    now = [1000.0]
    monkeypatch.setattr(se.time, "monotonic", lambda: now[0])

    errors: list[str] = []
    monkeypatch.setattr(se.log, "error", lambda msg: errors.append(msg))
    monkeypatch.setattr(se.log, "debug", lambda msg: None)

    exc = Exception("FATAL:  remaining connection slots are reserved for roles with the SUPERUSER attribute")
    for i in range(5):
        engine._report_transfer_error(f"/video/{i}", exc)

    assert len(errors) == 1
    assert "max_connections" in errors[0]

    now[0] += 61
    engine._report_transfer_error("/video/after-window", exc)
    assert len(errors) == 2


def test_connection_budget_clamps_to_low_server_capacity(monkeypatch):
    for key in (
        "DATABASE__POOL_SIZE",
        "DATABASE__MAX_OVERFLOW",
        "DATABASE__SCHEDULER_POOL_SIZE",
        "DATABASE__SCHEDULER_MAX_OVERFLOW",
        "DATABASE__SYNC_WORKERS",
        "DATABASE__MAX_CONNECTIONS",
        "DATABASE__CONNECTION_RESERVE",
        "DATABASE__EXTERNAL_CONNECTION_RESERVE",
        "DATABASE__API_CONNECTION_RESERVE",
    ):
        monkeypatch.delenv(key, raising=False)
    budget = load_connection_budget("postgresql", server_max_connections=20)
    assert budget.total_capacity <= budget.available_connections
    assert budget.main_pool_size + budget.main_max_overflow >= 1
    assert budget.scheduler_pool_size + budget.scheduler_max_overflow >= 1
    assert 1 <= budget.sync_workers <= budget.main_capacity


def test_connection_budget_keeps_defaults_when_server_has_room():
    budget = load_connection_budget("postgresql", server_max_connections=100)
    assert budget.main_capacity == 20
    assert budget.scheduler_capacity == 10
    assert budget.sync_workers == 4
    assert budget.is_valid is True


def test_connection_budget_never_exceeds_available():
    budget = ConnectionBudget(
        main_pool_size=20,
        main_max_overflow=20,
        scheduler_pool_size=10,
        scheduler_max_overflow=10,
        sync_workers=10,
        server_max_connections=30,
        reserved_connections=3,
        external_reserve=5,
    ).resolve()
    assert budget.total_capacity <= budget.available_connections
