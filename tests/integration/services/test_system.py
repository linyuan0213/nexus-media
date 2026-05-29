"""Tests for app.services.system package."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.system.backup import BackupRestoreService
from app.services.system.config import (
    ConfigUpdateService,
    SystemConfigService,
)
from app.services.system.info import (
    NetTestService,
    ProgressService,
    SystemInfoService,
    VersionService,
    WebSearchService,
    get_commands,
    get_rmt_modes,
    parse_brush_rule_string,
)
from app.services.system.lifecycle import SchedulerService, SystemLifecycleService
from app.services.system.message import (
    MessageClientService,
    MessageCommandHandler,
    MessageSenderService,
)
from app.utils.types import ProgressKey


class TestBackupRestoreService:
    """Test suite for BackupRestoreService."""

    def test_restore_from_backup_empty_filename(self):
        svc = BackupRestoreService()
        result = svc.restore_from_backup("")
        assert result.success is False
        assert "文件不存在" in result.message

    def test_backup_function(self):
        with (
            patch("app.services.system.backup.settings") as mock_settings,
            patch("app.services.system.backup.DatabaseFactory._get_config_db_type", return_value="sqlite"),
            patch("app.services.system.backup.DatabaseFactory.create_engine") as mock_engine,
            patch("pathlib.Path.mkdir"),
            patch("app.services.system.backup.shutil.copy"),
            patch("app.services.system.backup.export_to_file"),
            patch("app.services.system.backup.shutil.make_archive"),
            patch("app.services.system.backup.shutil.rmtree"),
        ):
            mock_settings.config_path = "/tmp/test_config"
            mock_engine.return_value.dispose = MagicMock()
            from app.services.system.backup import backup

            result = backup()
            assert result is not None
            assert result.endswith(".zip")


class TestSystemConfigService:
    """Test suite for SystemConfigService."""

    def test_set_config_success(self):
        config = MagicMock()
        svc = SystemConfigService(config)
        result = svc.set_config("test_key", "test_value")
        assert result is True
        config.set.assert_called_once_with(key="test_key", value="test_value")

    def test_set_config_empty_key(self):
        config = MagicMock()
        svc = SystemConfigService(config)
        result = svc.set_config("", "value")
        assert result is False

    def test_set_config_empty_value(self):
        config = MagicMock()
        svc = SystemConfigService(config)
        result = svc.set_config("key", None)
        assert result is False


class TestConfigUpdateService:
    """Test suite for ConfigUpdateService."""

    def test_update_config(self):
        with patch("app.services.system.config.settings") as mock_settings:
            mock_settings.get.return_value = {"test": "value"}
            result = ConfigUpdateService.update_config({"new_key": "new_value"})
            assert result.success is True
            mock_settings.save.assert_called_once()


class TestSystemInfoService:
    """Test suite for SystemInfoService."""

    def test_get_system_info(self):
        svc = SystemInfoService()
        result = svc.get_system_info()
        assert result.version is not None
        assert result.python_version is not None

    def test_format_uptime(self):
        svc = SystemInfoService()
        assert "天" in svc._format_uptime(90000)
        assert "小时" in svc._format_uptime(7200)
        assert "分钟" in svc._format_uptime(300)


class TestVersionService:
    """Test suite for VersionService."""

    def test_get_latest_version(self):
        with patch("app.services.system.info.WebUtils.get_latest_version", return_value=("1.0", "http://url", True)):
            svc = VersionService()
            result = svc.get_latest_version()
            assert result.has_update is True
            assert result.version == "1.0"

    def test_get_latest_version_no_update(self):
        with patch("app.services.system.info.WebUtils.get_latest_version", return_value=("", "", False)):
            svc = VersionService()
            result = svc.get_latest_version()
            assert result.has_update is False


class TestNetTestService:
    """Test suite for NetTestService."""

    def test_test_success(self):
        with patch("app.services.system.info.RequestUtils") as mock_req:
            mock_res = MagicMock()
            mock_res.ok = True
            mock_req.return_value.get_res.return_value = mock_res
            svc = NetTestService()
            result = svc.test("example.com")
            assert result.success is True

    def test_test_failure(self):
        with patch("app.services.system.info.RequestUtils") as mock_req:
            mock_req.return_value.get_res.return_value = None
            svc = NetTestService()
            result = svc.test("example.com")
            assert result.success is False


class TestWebSearchService:
    """Test suite for WebSearchService."""

    def test_search_empty(self):
        svc = WebSearchService()
        result = svc.search("")
        assert result.code == 0

    def test_search_with_results(self):
        search_fn = MagicMock(return_value=(0, "ok"))
        svc = WebSearchService(search_fn)
        result = svc.search("test")
        assert result.code == 0
        assert result.msg == "ok"


class TestProgressService:
    """Test suite for ProgressService."""

    def test_get_progress_exists(self):
        helper = MagicMock()
        helper.get_process.return_value = {"value": 50, "text": "half"}
        svc = ProgressService(helper)
        result = svc.get_progress(ProgressKey.Search.value)
        assert result.exists is True
        assert result.value == 50
        assert result.text == "half"

    def test_get_progress_not_exists(self):
        helper = MagicMock()
        helper.get_process.return_value = None
        svc = ProgressService(helper)
        result = svc.get_progress(ProgressKey.Search.value)
        assert result.exists is False


class TestSchedulerService:
    """Test suite for SchedulerService."""

    def test_start_service_known(self):
        with patch("app.services.system.lifecycle.container"):
            downloader = MagicMock()
            sync = MagicMock()
            rss = MagicMock()
            subscribe = MagicMock()
            thread_helper = MagicMock()
            svc = SchedulerService(downloader, sync, rss, subscribe, thread_helper)
            msg = svc.start_service("pttransfer")
            assert msg == "服务已启动"
            thread_helper.start_thread.assert_called_once()

    def test_start_service_unknown(self):
        from app.core.exceptions import ResourceNotFoundError

        with patch("app.services.system.lifecycle.container"):
            downloader = MagicMock()
            sync = MagicMock()
            rss = MagicMock()
            subscribe = MagicMock()
            thread_helper = MagicMock()
            svc = SchedulerService(downloader, sync, rss, subscribe, thread_helper)
            with pytest.raises(ResourceNotFoundError):
                svc.start_service("unknown")


class TestSystemLifecycleService:
    """Test suite for SystemLifecycleService."""

    def test_init(self):
        svc = SystemLifecycleService()
        assert svc._scheduler is not None


class TestMessageClientService:
    """Test suite for MessageClientService."""

    def test_delete_client(self):
        message = MagicMock()
        message.delete_message_client.return_value = True
        svc = MessageClientService(message)
        result = svc.delete_client(1)
        assert result is True
        message.delete_message_client.assert_called_once_with(cid=1)

    def test_get_client(self):
        message = MagicMock()
        message.get_message_client_info.return_value = {"id": 1}
        svc = MessageClientService(message)
        result = svc.get_client(1)
        assert result == {"id": 1}

    def test_toggle_interactive(self):
        message = MagicMock()
        svc = MessageClientService(message)
        result = svc.toggle_interactive(1, "telegram", True)
        assert result is True

    def test_toggle_enable(self):
        message = MagicMock()
        svc = MessageClientService(message)
        result = svc.toggle_enable(1, True)
        assert result is True

    def test_test_connection(self):
        message = MagicMock()
        message.get_status.return_value = True
        svc = MessageClientService(message)
        result = svc.test_connection("telegram", {})
        assert result is True


class TestMessageSenderService:
    """Test suite for MessageSenderService."""

    def test_send_custom_message_no_clients(self):
        svc = MessageSenderService(MagicMock())
        result = svc.send_custom_message([], "title", "text")
        assert result.success is False

    def test_send_custom_message_success(self):
        message = MagicMock()
        svc = MessageSenderService(message)
        result = svc.send_custom_message(["client1"], "title", "text")
        assert result.success is True
        message.send_custom_message.assert_called_once()

    def test_send_plugin_message(self):
        message = MagicMock()
        svc = MessageSenderService(message)
        result = svc.send_plugin_message("title", "text")
        assert result.success is True


class TestMessageCommandHandler:
    """Test suite for MessageCommandHandler."""

    def test_handle_message_job_empty(self):
        with patch("app.services.system.message.container"):
            handler = MessageCommandHandler(MagicMock())
            result = handler.handle_message_job("")
            assert result is None

    def test_commands_dict(self):
        with patch("app.services.system.message.container"):
            handler = MessageCommandHandler(
                MagicMock(),
                torrent_remover=MagicMock(),
                downloader=MagicMock(),
                sync_svc=MagicMock(),
                rss=MagicMock(),
                subscribe_svc=MagicMock(),
                filetransfer=MagicMock(),
            )
            assert "/ptr" in handler._command_map
            assert "/ptt" in handler._command_map
            assert "/rss" in handler._command_map


class TestUtilityFunctions:
    """Test suite for system module utility functions."""

    def test_get_commands(self):
        result = get_commands()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_rmt_modes(self):
        result = get_rmt_modes()
        assert isinstance(result, list)
        assert any(r["value"] == "copy" for r in result)
        assert any(r["value"] == "move" for r in result)

    def test_parse_brush_rule_string_none(self):
        result = parse_brush_rule_string(None)
        assert result == ""

    def test_parse_brush_rule_string_empty(self):
        result = parse_brush_rule_string({})
        assert result == ""
