"""AutoBackup 插件保留策略测试."""

from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autobackup.backend.plugin import (
    AutoBackupPlugin,
    _is_backup_file,
)


class TestAutoBackupRetention:
    def test_recognizes_new_and_legacy_names(self):
        assert _is_backup_file("nexus_media_backup_2026-11-13_17-50-51.zip")
        assert _is_backup_file("bk_20261113175051.zip")
        assert not _is_backup_file("other.zip")
        assert not _is_backup_file("nexus_media_backup_2026-11-13_17-50-51.tar")

    def test_local_retention_removes_old_backups(self, tmp_path):
        for index in range(3):
            (tmp_path / f"bk_2026111317505{index}.zip").write_bytes(b"old")
        current = tmp_path / "nexus_media_backup_2026-11-13_18-00-00.zip"
        current.write_bytes(b"new")

        ctx = MagicMock()
        ctx.get_config.return_value = {
            "enabled": True,
            "storage_type": "local",
            "bk_path": str(tmp_path),
            "cnt": 2,
        }
        plugin = AutoBackupPlugin(ctx)
        with patch(
            "app.plugin_framework.builtin_plugins.autobackup.backend.plugin.do_backup",
            return_value=str(current),
        ):
            plugin._do_backup(manual=True)

        remaining = [p.name for p in tmp_path.iterdir() if _is_backup_file(p.name)]
        assert len(remaining) == 2
        assert current.name in remaining
        assert not (tmp_path / "bk_20261113175050.zip").exists()
