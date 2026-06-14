"""存储后端 IO 优化单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.storage import LocalStorageBackend, StorageConfig
from app.storage.backends.base import StorageType
from app.storage.cross_backend import cross_copy


class TestCrossBackend:
    """测试跨后端复制."""

    def test_cross_copy_uses_fast_copy_when_available(self, tmp_path):
        """当后端支持 fast cross copy 时优先使用."""
        src = tmp_path / "src.bin"
        src.write_bytes(b"hello")
        dst = tmp_path / "dst.bin"

        src_backend = MagicMock()
        src_backend.can_fast_cross_copy.return_value = True
        src_backend.read_stream.return_value = open(src, "rb")

        dst_backend = MagicMock()
        dst_backend.write_stream = MagicMock()

        cross_copy(src_backend, str(src), dst_backend, str(dst))

        src_backend.cross_copy_to.assert_called_once_with(str(src), dst_backend, str(dst))
        dst_backend.write_stream.assert_not_called()

    def test_cross_copy_fallback_to_stream(self, tmp_path):
        """不支持 fast copy 时回退到流式传输."""
        src = tmp_path / "src.bin"
        src.write_bytes(b"hello world")
        dst = tmp_path / "dst.bin"

        src_backend = MagicMock()
        src_backend.can_fast_cross_copy.return_value = False
        stream_mock = MagicMock()
        stream_mock.read.return_value = b"hello world"
        src_backend.read_stream.return_value = stream_mock

        dst_backend = MagicMock()
        dst_backend.write_stream = MagicMock()

        cross_copy(src_backend, str(src), dst_backend, str(dst))

        dst_backend.write_stream.assert_called_once_with(str(dst), stream_mock)
        stream_mock.close.assert_called_once()


class TestLocalStorageBackend:
    """测试本地存储后端写流优化."""

    def test_write_stream_copies_data(self, tmp_path):
        """write_stream 应正确写入数据."""
        backend = LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        src = tmp_path / "src.bin"
        src.write_bytes(b"abc")
        dst = tmp_path / "dst.bin"

        with open(src, "rb") as f:
            backend.write_stream(str(dst), f)

        assert dst.read_bytes() == b"abc"

    def test_write_stream_creates_parent_dirs(self, tmp_path):
        """write_stream 应自动创建父目录."""
        backend = LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        src = tmp_path / "src.bin"
        src.write_bytes(b"x")
        dst = tmp_path / "sub" / "dir" / "dst.bin"

        with open(src, "rb") as f:
            backend.write_stream(str(dst), f)

        assert dst.read_bytes() == b"x"

    def test_copy_uses_sendfile_fast_path(self, tmp_path):
        """同后端 copy 应使用 shutil.copy2（底层可能走 sendfile）."""
        backend = LocalStorageBackend(StorageConfig(id="local", name="local", type=StorageType.LOCAL))
        src = tmp_path / "src.bin"
        data = b"a" * (1024 * 1024 + 1)  # 超过 1MB
        src.write_bytes(data)
        dst = tmp_path / "dst.bin"

        with patch("shutil.copy2") as mock_copy2:
            backend.copy(str(src), str(dst))
            mock_copy2.assert_called_once()
