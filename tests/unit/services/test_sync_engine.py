"""SyncEngine 单元测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.sync_engine import FileMonitorHandler, SyncEngine, SyncPathConfig, _synced_lock
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


def _history_rec(dest_path: str, dest_filename: str, source_path: str = "", source_filename: str = "", date: str = ""):
    """构造转移历史记录 stub（仅需目录目标存在性判定用到的字段）."""
    return SimpleNamespace(
        dest_path=dest_path,
        dest_filename=dest_filename,
        source_path=source_path,
        source_filename=source_filename,
        date=date,
    )


@pytest.fixture
def engine(tmp_path):
    transfer_engine = MagicMock()
    transfer_engine._blacklist = MagicMock()
    transfer_engine._blacklist.is_exists.return_value = False
    pipeline = MagicMock()
    sync_repo = MagicMock()
    sync_repo.get_config_sync_paths.return_value = []
    backend_repo = MagicMock()
    with patch("app.services.sync_engine.TransferHistoryRepositoryAdapter") as mock_history_cls:
        mock_history = MagicMock()
        mock_history.is_sync_in_history.return_value = False
        mock_history_cls.return_value = mock_history
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

    def test_do_transfer_skips_blacklisted(self, engine, tmp_path):
        """已转移过（黑名单命中）且目标仍存在的路径应跳过，避免每个扫描周期重复处理."""
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.source = str(tmp_path / "src")
        cfg.dest = str(tmp_path / "dst")
        eng._transfer._blacklist.is_exists.return_value = True
        with patch.object(eng, "_destination_exists_for_source", return_value=True):
            eng._do_transfer(str(tmp_path / "src" / "movie.mkv"), cfg)
        eng._pipeline.process.assert_not_called()

    def test_do_transfer_skips_synced_history(self, engine, tmp_path):
        """同步历史命中且目标仍存在时也应跳过."""
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.dest = str(tmp_path / "dst")
        eng._history_repo.is_sync_in_history.return_value = True
        with patch.object(eng, "_destination_exists_for_source", return_value=True):
            eng._do_transfer(str(tmp_path / "src" / "movie.mkv"), cfg)
        eng._pipeline.process.assert_not_called()

    def test_do_transfer_relinks_when_target_missing(self, engine, tmp_path):
        """回归：rename/转移模式下目标被删除，命中黑名单也应清理并重新同步（重新硬链接）."""
        eng, _, _ = engine
        src = tmp_path / "src"
        src.mkdir()
        (src / "movie.mkv").write_text("x", encoding="utf-8")
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(tmp_path / "dst")
        eng._transfer._blacklist.is_exists.return_value = True
        eng._pipeline.process.return_value = (True, "ok")
        with patch.object(eng, "_destination_exists_for_source", return_value=False):
            eng._do_transfer(str(src / "movie.mkv"), cfg)
        eng._transfer._blacklist.delete.assert_called_once()
        eng._pipeline.process.assert_called_once()

    def test_do_transfer_relinks_dir_when_target_missing(self, engine, tmp_path):
        """回归 #196：目录来源命中黑名单但目标已被删除时，应清理并重新同步（重新硬链接）."""
        eng, _, _ = engine
        src = tmp_path / "src"
        movie_dir = src / "Movie.2020"
        movie_dir.mkdir(parents=True)
        (movie_dir / "E01.mkv").write_text("x", encoding="utf-8")
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(tmp_path / "lib")
        eng._transfer._blacklist.is_exists.return_value = True
        eng._pipeline.process.return_value = (True, "ok")
        # 目录内文件曾生成于 /lib（转移历史），但目标已被删除
        eng._history_repo.get_by_source_dir.return_value = [_history_rec(str(tmp_path / "lib" / "Movie"), "E01.mkv")]

        eng._do_transfer(str(movie_dir), cfg)

        eng._pipeline.process.assert_called_once()
        eng._transfer._blacklist.delete.assert_any_call(str(movie_dir))

    def test_do_transfer_skips_dir_when_target_present(self, engine, tmp_path):
        """目录来源命中黑名单且目标仍存在时跳过，避免每个扫描周期重复处理."""
        eng, _, _ = engine
        src = tmp_path / "src"
        movie_dir = src / "Movie.2020"
        movie_dir.mkdir(parents=True)
        (movie_dir / "E01.mkv").write_text("x", encoding="utf-8")
        dest_dir = tmp_path / "lib" / "Movie"
        dest_dir.mkdir(parents=True)
        (dest_dir / "E01.mkv").write_text("y", encoding="utf-8")
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(tmp_path / "lib")
        eng._transfer._blacklist.is_exists.return_value = True
        eng._history_repo.get_by_source_dir.return_value = [_history_rec(str(dest_dir), "E01.mkv")]

        eng._do_transfer(str(movie_dir), cfg)

        eng._pipeline.process.assert_not_called()

    def test_do_transfer_relinks_dir_when_any_target_missing(self, engine, tmp_path):
        """目录内任一文件的目标被删除即应重新同步（部分删除场景）."""
        eng, _, _ = engine
        src = tmp_path / "src"
        movie_dir = src / "Show" / "S01"
        movie_dir.mkdir(parents=True)
        for name in ("E01.mkv", "E02.mkv"):
            (movie_dir / name).write_text("x", encoding="utf-8")
        dest_dir = tmp_path / "lib" / "Show" / "S01"
        dest_dir.mkdir(parents=True)
        (dest_dir / "E01.mkv").write_text("y", encoding="utf-8")  # E02 的目标缺失
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(tmp_path / "lib")
        eng._transfer._blacklist.is_exists.return_value = True
        eng._pipeline.process.return_value = (True, "ok")
        eng._history_repo.get_by_source_dir.return_value = [
            _history_rec(str(dest_dir), "E01.mkv", str(movie_dir), "E01.mkv", "2024-01-01 10:00:00"),
            _history_rec(str(dest_dir), "E02.mkv", str(movie_dir), "E02.mkv", "2024-01-01 10:00:00"),
        ]

        eng._do_transfer(str(movie_dir), cfg)

        eng._pipeline.process.assert_called_once()

    def test_do_transfer_uses_latest_history_for_same_source(self, engine, tmp_path):
        """同一源文件有多条历史时以最近一次为准，旧目标缺失不误判为需重建."""
        eng, _, _ = engine
        src = tmp_path / "src"
        movie_dir = src / "Movie.2020"
        movie_dir.mkdir(parents=True)
        (movie_dir / "E01.mkv").write_text("x", encoding="utf-8")
        dest_dir = tmp_path / "lib" / "Movie"
        dest_dir.mkdir(parents=True)
        (dest_dir / "E01.mkv").write_text("y", encoding="utf-8")
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(tmp_path / "lib")
        eng._transfer._blacklist.is_exists.return_value = True
        eng._history_repo.get_by_source_dir.return_value = [
            _history_rec(str(dest_dir), "E01.mkv", str(movie_dir), "E01.mkv", "2024-01-02 10:00:00"),
            _history_rec(str(tmp_path / "old" / "Movie"), "E01.mkv", str(movie_dir), "E01.mkv", "2024-01-01 10:00:00"),
        ]

        eng._do_transfer(str(movie_dir), cfg)

        eng._pipeline.process.assert_not_called()

    def test_do_transfer_relinks_dir_without_dir_blacklist(self, engine, tmp_path):
        """目录未入黑名单但内部文件已入黑名单、目标被删除时，也应清理文件黑名单并重新同步."""
        eng, _, _ = engine
        src = tmp_path / "src"
        movie_dir = src / "Movie.2020"
        movie_dir.mkdir(parents=True)
        file_path = movie_dir / "E01.mkv"
        file_path.write_text("x", encoding="utf-8")
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(tmp_path / "lib")
        eng._transfer._blacklist.is_exists.side_effect = lambda p: p == str(file_path)
        eng._pipeline.process.return_value = (True, "ok")
        eng._history_repo.get_by_source_dir.return_value = [_history_rec(str(tmp_path / "lib" / "Movie"), "E01.mkv")]

        eng._do_transfer(str(movie_dir), cfg)

        eng._pipeline.process.assert_called_once()
        eng._transfer._blacklist.delete.assert_any_call(str(file_path))

    def test_directory_destination_exists_without_history(self, engine, tmp_path):
        """目录无转移历史时无法判定，按目标存在处理，避免误判为需重建."""
        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.dest = str(tmp_path / "lib")
        eng._history_repo.get_by_source_dir.return_value = []
        assert eng._directory_destination_exists(str(tmp_path / "src"), cfg) is True

    def test_do_link_relinks_when_history_hit_but_target_missing(self, engine, tmp_path):
        """回归 #193：目标媒体文件被删除后，命中历史也应清理并重新硬链接."""
        eng, _, _ = engine
        eng._history_repo.is_sync_in_history.return_value = True
        src = tmp_path / "src"
        src.mkdir()
        dst_root = tmp_path / "dst"
        dst_root.mkdir()
        src_file = src / "movie.mkv"
        src_file.write_text("x", encoding="utf-8")  # 目标 dst/movie.mkv 不存在
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(dst_root)
        cfg.operation = "link"

        eng._do_link(str(src_file), cfg)

        eng._history_repo.delete_sync_history.assert_called_once_with(str(src_file), str(dst_root))
        eng._transfer._execute.assert_called_once()

    def test_do_link_skips_when_target_exists(self, engine, tmp_path):
        eng, _, _ = engine
        eng._history_repo.is_sync_in_history.return_value = True
        src = tmp_path / "src"
        src.mkdir()
        dst_root = tmp_path / "dst"
        dst_root.mkdir()
        src_file = src / "movie.mkv"
        src_file.write_text("x", encoding="utf-8")
        (dst_root / "movie.mkv").write_text("y", encoding="utf-8")  # 目标存在
        cfg = SyncPathConfig(_Row())
        cfg.source = str(src)
        cfg.dest = str(dst_root)
        cfg.operation = "link"

        eng._do_link(str(src_file), cfg)

        eng._history_repo.delete_sync_history.assert_not_called()
        eng._transfer._execute.assert_not_called()

    def test_transfer_sync_parallel(self, engine, tmp_path):
        """transfer_sync 应使用线程池并发处理多个文件."""
        from concurrent.futures import Future

        eng, _, _ = engine
        cfg = SyncPathConfig(_Row())
        cfg.source = str(tmp_path / "src")
        cfg.dest = str(tmp_path / "dst")
        cfg.rename = False
        eng._configs["1"] = cfg
        eng._monitor_ids = ["1"]
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        for name in ("a.mkv", "b.mkv", "c.mkv"):
            (src_dir / name).write_text("x")

        submitted = []

        def fake_submit(func, *args, **kwargs):
            submitted.append(args)
            future = Future()
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                future.set_exception(e)
            else:
                future.set_result(result)
            return future

        mock_executor = MagicMock()
        mock_executor.submit.side_effect = fake_submit
        eng._thread_executor = mock_executor
        eng._sync_workers = 4

        with patch("app.services.sync_engine.get_lock_manager") as mock_lock_mgr:
            lock = MagicMock()
            lock.acquire.return_value = True
            mock_lock_mgr.return_value.create_lock.return_value = lock
            eng.transfer_sync(sid="1")

        assert len(submitted) == 3
        eng._transfer._execute.assert_called()

    def test_backend_cache_reused(self, engine):
        """非 local 后端实例应被缓存复用."""
        eng, _, backend_repo = engine
        entity = MagicMock()
        entity.id = 2
        entity.name = "smb"
        entity.type = "smb"
        entity.enabled = True
        entity.config = {"server": "nas.local"}
        backend_repo.get_by_id.return_value = entity

        with patch.object(eng, "_build_storage_config", return_value=MagicMock()):
            with patch("app.services.sync_engine.StorageBackendFactory.create") as mock_create:
                backend = MagicMock()
                backend.name = "smb"
                mock_create.return_value = backend
                b1 = eng._resolve_backend("2")
                b2 = eng._resolve_backend("2")
                assert b1 is b2
                backend_repo.get_by_id.assert_called_once()

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

    def test_synced_files_fifo_eviction(self, engine):
        """_synced_files 应使用 FIFO 策略，避免旧条目长期驻留."""
        eng, _, _ = engine
        eng._synced_files_max_size = 3
        for i in range(5):
            with _synced_lock:
                eng._synced_files[f"/path/{i}"] = None
                if len(eng._synced_files) > eng._synced_files_max_size:
                    eng._synced_files.popitem(last=False)
        assert list(eng._synced_files.keys()) == ["/path/2", "/path/3", "/path/4"]

    def test_transfer_sync_skips_already_synced_files(self, engine, tmp_path):
        """transfer_sync 应跳过事件触发已处理的文件，避免重复同步."""
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
        # 模拟该文件已被事件触发处理过
        eng._synced_files[str(src_dir / "movie.mkv")] = None
        with patch("app.services.sync_engine.get_lock_manager") as mock_lock_mgr:
            lock = MagicMock()
            lock.acquire.return_value = True
            mock_lock_mgr.return_value.create_lock.return_value = lock
            eng.transfer_sync(sid="1")
            eng._transfer._execute.assert_not_called()

    def test_on_file_event_tracks_in_progress_files(self, engine, tmp_path):
        """on_file_event 应将处理中的文件加入 _synced_files，便于并发去重."""
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

        # 模拟 _do_link 卡住，验证文件仍在 _synced_files 中
        def slow_link(*args, **kwargs):
            with _synced_lock:
                assert str(f) in eng._synced_files

        eng._do_link = slow_link
        eng.on_file_event(str(f))
