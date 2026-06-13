"""SystemUtils 单元测试."""

import os
from unittest.mock import MagicMock, patch

from app.domain.enums import OsType
from app.utils.system_utils import SystemUtils


class TestSystemUtils:
    def test_get_system_linux(self):
        with patch("app.utils.system_utils.SystemUtils.is_windows", return_value=False):
            with patch("app.utils.system_utils.SystemUtils.is_synology", return_value=False):
                with patch("app.utils.system_utils.SystemUtils.is_docker", return_value=False):
                    with patch("app.utils.system_utils.SystemUtils.is_macos", return_value=False):
                        assert SystemUtils.get_system() == OsType.LINUX

    def test_get_system_windows(self):
        with patch("app.utils.system_utils.SystemUtils.is_windows", return_value=True):
            assert SystemUtils.get_system() == OsType.WINDOWS

    def test_get_local_time(self):
        result = SystemUtils.get_local_time("2024-01-01T00:00:00.000Z")
        assert "2024-01-01" in result

    def test_get_local_time_invalid(self):
        assert SystemUtils.get_local_time("invalid") == "invalid"

    def test_check_process(self):
        with patch("app.utils.system_utils.psutil.process_iter") as mock_iter:
            proc = MagicMock()
            proc.name.return_value = "python"
            mock_iter.return_value = [proc]
            assert SystemUtils.check_process("python") is True
            assert SystemUtils.check_process("missing") is False

    def test_execute(self):
        with patch("app.utils.system_utils.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "output\n"
            assert SystemUtils.execute("echo hello") == "output"

    def test_execute_failure(self):
        with patch("app.utils.system_utils.subprocess.run", side_effect=Exception("err")):
            assert SystemUtils.execute("bad") == ""

    def test_is_docker(self, tmp_path):
        with patch("app.utils.system_utils.os.path.exists", return_value=False):
            assert SystemUtils.is_docker() is False

    def test_is_synology(self):
        with patch("app.utils.system_utils.SystemUtils.is_windows", return_value=False):
            with patch("app.utils.system_utils.SystemUtils.execute", return_value="Linux synology"):
                assert SystemUtils.is_synology() is True

    def test_is_macos(self):
        with patch("app.utils.system_utils.platform.system", return_value="Darwin"):
            assert SystemUtils.is_macos() is True

    def test_copy(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        dst = tmp_path / "dst.txt"
        code, msg = SystemUtils.copy(str(src), str(dst))
        assert code == 0
        assert dst.read_text() == "x"

    def test_copy_failure(self, tmp_path):
        code, msg = SystemUtils.copy("/nonexistent", str(tmp_path / "dst.txt"))
        assert code == -1

    def test_get_free_space(self, tmp_path):
        free = SystemUtils.get_free_space(str(tmp_path))
        assert free > 0

    def test_get_total_space(self, tmp_path):
        total = SystemUtils.get_total_space(str(tmp_path))
        assert total > 0

    def test_calculate_space_usage(self, tmp_path):
        result = SystemUtils.calculate_space_usage([str(tmp_path)])
        assert isinstance(result, tuple)
        total, free = result
        assert total > 0
        assert free > 0

    def test_calculate_space_usage_empty(self):
        result = SystemUtils.calculate_space_usage([])
        assert result == 0.0

    def test_get_all_processes(self):
        processes = SystemUtils.get_all_processes()
        assert isinstance(processes, list)

    def test_find_hardlinks(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        dst = tmp_path / "dst.txt"
        os.link(str(src), str(dst))
        result = SystemUtils().find_hardlinks(str(src))
        assert len(result) >= 1
        os.unlink(str(dst))

    def test_find_hardlinks_no_links(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("x")
        result = SystemUtils().find_hardlinks(str(src))
        assert result == []
