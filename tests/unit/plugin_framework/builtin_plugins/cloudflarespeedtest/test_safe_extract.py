"""CloudflareSpeedTest 安全解压函数单元测试"""

import tarfile
import zipfile
from io import BytesIO

from app.plugin_framework.builtin_plugins.cloudflarespeedtest.backend.plugin import (
    _safe_extractall,
    _safe_zip_extractall,
)


class TestSafeExtractAll:
    def test_safe_extractall_allows_normal_member(self, tmp_path):
        archive_path = tmp_path / "test.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            data = b"hello"
            info = tarfile.TarInfo(name="normal.txt")
            info.size = len(data)
            tar.addfile(info, BytesIO(data))

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, str(extract_dir))

        assert (extract_dir / "normal.txt").read_text() == "hello"

    def test_safe_extractall_blocks_path_traversal(self, tmp_path):
        archive_path = tmp_path / "evil.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            data = b"evil"
            info = tarfile.TarInfo(name="../evil.txt")
            info.size = len(data)
            tar.addfile(info, BytesIO(data))

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, str(extract_dir))

        assert not (tmp_path / "evil.txt").exists()

    def test_safe_extractall_blocks_absolute_path(self, tmp_path):
        archive_path = tmp_path / "abs.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            data = b"abs"
            info = tarfile.TarInfo(name="/tmp/abs.txt")
            info.size = len(data)
            tar.addfile(info, BytesIO(data))

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, str(extract_dir))

        assert not (extract_dir / "abs.txt").exists()


class TestSafeZipExtractAll:
    def test_safe_zip_extractall_allows_normal_member(self, tmp_path):
        archive_path = tmp_path / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("normal.txt", "hello")

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive_path, "r") as zf:
            _safe_zip_extractall(zf, str(extract_dir))

        assert (extract_dir / "normal.txt").read_text() == "hello"

    def test_safe_zip_extractall_blocks_path_traversal(self, tmp_path):
        archive_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("../evil.txt", "evil")

        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive_path, "r") as zf:
            _safe_zip_extractall(zf, str(extract_dir))

        assert not (tmp_path / "evil.txt").exists()
