"""SyncEngine 单元测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.sync_engine import FileMonitorHandler, SyncEngine, SyncPathConfig
from app.storage.backends.local import LocalStorageBackend


class _Row:
    ID = 1
    SOURCE = "/src"
    DEST = "/dst"
    UNKNOWN = "/unknown"
    OPERATION = "copy"
    SRC_BACKEND = "local"
    DST_BACKEND = "local"
    RENAME = 0
    COMPATIBILITY = 0
    ENABLED = 1


@pytest.fixture
def engine(tmp_path):
    transfer_engine = MagicMock()
    transfer_engine._blacklist = MagicMock()
    pipeline = MagicMock()
    sync_repo = MagicMock()
    sync_repo.get_config_sync_paths.return_value = []
    backend_repo = MagicMock()
    eng = SyncEngine(
        transfer_engine=transfer_engine,
        transfer_pipeline=pipeline,
        sync_path_repo=sync_repo,
        storage_backend_repo=backend_repo,
    )
    return eng, sync_repo, backend_repo


class TestSyncPathConfig:
    def test_config_defaults(self):
        cfg = SyncPathConfig(_Row())
        assert cfg.id == "1"
        assert cfg.source == "/src"
        assert cfg.dest == "/dst"
        assert cfg.operation == "copy"
        assert cfg.src_backend_id == "local"
        assert cfg.dst_backend_id == "local"
        assert cfg.rename is False
        assert cfg.enabled is True


class TestSyncEngine:
    def test_init(self, engine):
        eng, sync_repo, _ = engine
        assert eng._configs == {}
        assert eng._monitor_ids == []
        sync_repo.get_config_sync_paths.assert_called_once()

    def test_get_sync_path_conf(self, engine):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        eng._configs["1"] = cfg
        assert eng.get_sync_path_conf("1") is cfg
        assert eng.get_sync_path_conf("missing") is None

    def test_get_all_sync_path_conf(self, engine):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        eng._configs["1"] = cfg
        assert eng.get_all_sync_path_conf() == {"1": cfg}

    def test_resolve_backend_local(self, engine):
        eng, _, _ = engine
        backend = eng._resolve_backend("local")
        assert isinstance(backend, LocalStorageBackend)

    def test_resolve_backend_missing(self, engine):
        eng, _, backend_repo = engine
        backend_repo.get_by_id.return_value = None
        with pytest.raises(ValueError):
            eng._resolve_backend("999")

    def test_build_storage_config(self, engine):
        eng, _, _ = engine
        entity = MagicMock()
        entity.id = 2
        entity.name = "smb"
        entity.type = "smb"
        entity.enabled = True
        entity.config = {"server": "nas.local", "username": "u"}
        cfg = eng._build_storage_config(entity)
        assert cfg.id == "2"
        assert cfg.name == "smb"
        assert cfg.server == "nas.local"
        assert cfg.username == "u"

    def test_find_config(self, engine):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        eng._configs["1"] = cfg
        eng._monitor_ids = ["1"]
        found = eng._find_config("/src/movie.mkv")
        assert found is cfg

    def test_find_config_nested(self, engine):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        eng._configs["1"] = cfg
        eng._monitor_ids = ["1"]
        assert eng._find_config("/dst/file.mkv") is None

    def test_on_file_event_skip_invalid_path(self, engine):
        eng, _, _ = engine
        with patch.object(eng, "_find_config", return_value=None):
            eng.on_file_event("/some/path.mkv")

    def test_on_file_event_do_link(self, engine, tmp_path):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.source = str(tmp_path / "src")
        cfg.dest = str(tmp_path / "dst")
        cfg.rename = False
        eng._configs["1"] = cfg
        eng._monitor_ids = ["1"]
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        f = src_dir / "movie.mkv"
        f.write_text("x")
        eng.on_file_event(str(f))
        eng._transfer._execute.assert_called_once()

    def test_on_file_event_do_transfer(self, engine, tmp_path):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.source = str(tmp_path / "src")
        cfg.dest = str(tmp_path / "dst")
        cfg.rename = True
        eng._configs["1"] = cfg
        eng._monitor_ids = ["1"]
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        f = src_dir / "movie.mkv"
        f.write_text("x")
        eng.on_file_event(str(f))
        eng._pipeline.process.assert_called_once()

    def test_transfer_sync_with_sid(self, engine, tmp_path):
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.source = str(tmp_path / "src")
        cfg.dest = str(tmp_path / "dst")
        cfg.rename = False
        eng._configs["1"] = cfg
        eng._monitor_ids = ["1"]
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "movie.mkv").write_text("x")
        with patch("app.services.sync_engine.get_lock_manager") as mock_lock_mgr:
            lock = MagicMock()
            lock.acquire.return_value = True
            mock_lock_mgr.return_value.create_lock.return_value = lock
            eng.transfer_sync(sid="1")
            eng._transfer._execute.assert_called_once()

    def test_transfer_sync_lock_not_acquired(self, engine):
        with patch("app.services.sync_engine.get_lock_manager") as mock_lock_mgr:
            lock = MagicMock()
            lock.acquire.return_value = False
            mock_lock_mgr.return_value.create_lock.return_value = lock
            eng, _, _ = engine
            eng.transfer_sync()
            lock.acquire.assert_called_once()

    def test_delete_sync_path(self, engine):
        eng, sync_repo, _ = engine
        sync_repo.delete_config_sync_path.return_value = True
        with patch.object(eng, "init"):
            assert eng.delete_sync_path(1) is True
            sync_repo.delete_config_sync_path.assert_called_once_with(sid=1)

    def test_insert_sync_path(self, engine):
        eng, sync_repo, _ = engine
        sync_repo.insert_config_sync_path.return_value = True
        with patch.object(eng, "init"):
            assert eng.insert_sync_path(source="/s", dest="/d") is True
            sync_repo.insert_config_sync_path.assert_called_once_with(source="/s", dest="/d")

    def test_check_sync_paths(self, engine):
        eng, sync_repo, _ = engine
        sync_repo.check_config_sync_paths.return_value = True
        with patch.object(eng, "init"):
            assert eng.check_sync_paths(source="/s") is True

    def test_check_source_disable_duplicate(self, engine):
        eng, sync_repo, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.source = "/src"
        cfg.dest = "/dst"
        eng._configs["1"] = cfg
        eng.check_source(source="/src")
        sync_repo.check_config_sync_paths.assert_called_once_with(sid="1", enabled=False)

    def test_file_monitor_handler(self, engine):
        eng, _, _ = engine
        handler = FileMonitorHandler("/src", eng)
        with patch.object(eng, "on_file_event") as mock:
            handler.on_created(MagicMock(src_path="/src/file.mkv"))
            mock.assert_called_once_with("/src/file.mkv")
            handler.on_moved(MagicMock(dest_path="/src/file2.mkv"))
            assert mock.call_count == 2

    def test_stop(self, engine):
        eng, _, _ = engine
        obs = MagicMock()
        eng._observers = [obs]
        eng.stop()
        obs.stop.assert_called_once()
        obs.join.assert_called_once()
        assert eng._observers == []
