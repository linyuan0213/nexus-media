"""Storage backend 基础类型与本地后端单元测试."""

import os
from io import BytesIO

import pytest

from app.storage.backends.base import FileInfo, StorageBackend, StorageConfig, StorageType
from app.storage.backends.local import LocalStorageBackend


class DummyConfig(StorageConfig):
    pass


class TestStorageBase:
    def test_storage_type_values(self):
        assert StorageType.LOCAL.name == "LOCAL"
        assert StorageType.WEBDAV.name == "WEBDAV"

    def test_file_info_defaults(self):
        info = FileInfo(path="/a", size=10, mtime=1.0, is_dir=False)
        assert info.mime_type == ""

    def test_storage_config_fields_empty(self):
        assert DummyConfig.get_fields() == []

    def test_storage_backend_can_fast_cross_copy_default(self):
        backend = LocalStorageBackend(config=StorageConfig(id="x", name="x", type=StorageType.LOCAL))
        assert backend.can_fast_cross_copy(backend) is False

    def test_storage_backend_cross_copy_raises(self):
        backend = LocalStorageBackend(config=StorageConfig(id="x", name="x", type=StorageType.LOCAL))
        with pytest.raises(NotImplementedError):
            backend.cross_copy_to("/src", backend, "/dst")

    def test_storage_backend_health_check_default(self):
        class DummyBackend(StorageBackend):
            def exists(self, path: str) -> bool:
                return True

            def stat(self, path: str) -> FileInfo | None:
                return None

            def list_dir(self, path: str):
                yield from ()

            def mkdir(self, path: str, parents: bool = True) -> None:
                return None

            def remove(self, path: str, recursive: bool = False) -> None:
                return None

            def read_stream(self, path: str):
                return BytesIO(b"")

            def write_stream(self, path: str, stream, size: int = 0, chunk_size: int = 0) -> None:
                return None

            def copy(self, src: str, dst: str) -> None:
                return None

            def move(self, src: str, dst: str) -> None:
                return None

        backend = DummyBackend(config=StorageConfig(id="x", name="x", type=StorageType.LOCAL))
        assert backend.health_check() == (True, "ok")


class TestLocalStorageBackend:
    @pytest.fixture
    def backend(self):
        return LocalStorageBackend(config=StorageConfig(id="local", name="local", type=StorageType.LOCAL))

    def test_exists(self, backend, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        assert backend.exists(str(f)) is True
        assert backend.exists(str(tmp_path / "missing")) is False

    def test_stat(self, backend, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello")
        info = backend.stat(str(f))
        assert info is not None
        assert info.size == 5
        assert info.is_dir is False

    def test_stat_missing(self, backend, tmp_path):
        assert backend.stat(str(tmp_path / "missing")) is None

    def test_list_dir(self, backend, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "dir").mkdir()
        items = list(backend.list_dir(str(tmp_path)))
        names = {os.path.basename(i.path) for i in items}
        assert "file.txt" in names
        assert "dir" in names
        file_info = next(i for i in items if os.path.basename(i.path) == "file.txt")
        assert file_info.is_dir is False

    def test_write_and_read_stream(self, backend, tmp_path):
        target = tmp_path / "nested" / "out.bin"
        backend.write_stream(str(target), BytesIO(b"data"))
        with backend.read_stream(str(target)) as f:
            assert f.read() == b"data"

    def test_mkdir(self, backend, tmp_path):
        d = tmp_path / "new" / "dir"
        backend.mkdir(str(d))
        assert d.exists()

    def test_remove_file(self, backend, tmp_path):
        f = tmp_path / "del.txt"
        f.write_text("x")
        backend.remove(str(f))
        assert not f.exists()

    def test_remove_dir_recursive(self, backend, tmp_path):
        d = tmp_path / "d"
        d.mkdir()
        (d / "f.txt").write_text("x")
        backend.remove(str(d), recursive=True)
        assert not d.exists()

    def test_remove_root_guard(self, backend):
        with pytest.raises(ValueError):
            backend.remove("/")

    def test_copy(self, backend, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("copy")
        dst = tmp_path / "dst.txt"
        backend.copy(str(src), str(dst))
        assert dst.read_text() == "copy"

    def test_move(self, backend, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("move")
        dst = tmp_path / "dst.txt"
        backend.move(str(src), str(dst))
        assert dst.read_text() == "move"
        assert not src.exists()

    def test_hardlink(self, backend, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("link")
        dst = tmp_path / "dst.txt"
        backend.hardlink(str(src), str(dst))
        assert dst.exists()
        assert os.path.samefile(src, dst)

    def test_softlink(self, backend, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("symlink")
        dst = tmp_path / "dst.txt"
        backend.softlink(str(src), str(dst))
        assert dst.is_symlink()
        assert os.readlink(dst) == str(src)

    def test_health_check(self, backend):
        assert backend.health_check() == (True, "本地文件系统")
