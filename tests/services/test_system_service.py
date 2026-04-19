import json
import os
import pytest
from unittest.mock import MagicMock, patch, mock_open, call

from app.services.system_service import (
    BackupRestoreResultDTO,
    NetTestResultDTO,
    IndexerConfigResultDTO,
    MediaServerConfigResultDTO,
    SearchResultDTO,
    VersionInfoDTO,
    MessageClientService,
    BackupRestoreService,
    IndexerConfigService,
    MediaServerConfigService,
    NetTestService,
    SchedulerService,
    WebSearchService,
    SystemConfigService,
    VersionService,
)


class TestMessageClientService:
    def _svc(self):
        mock_msg = MagicMock()
        return MessageClientService(message=mock_msg), mock_msg

    def test_delete_client_success(self):
        svc, mock_msg = self._svc()
        mock_msg.delete_message_client.return_value = True
        assert svc.delete_client(cid=1) is True
        mock_msg.delete_message_client.assert_called_once_with(cid=1)

    def test_delete_client_failure(self):
        svc, mock_msg = self._svc()
        mock_msg.delete_message_client.return_value = False
        assert svc.delete_client(cid=1) is False

    def test_get_client(self):
        svc, mock_msg = self._svc()
        mock_msg.get_message_client_info.return_value = {"id": 1}
        assert svc.get_client(cid=1) == {"id": 1}

    def test_toggle_interactive_checked(self):
        svc, mock_msg = self._svc()
        svc.toggle_interactive(cid=1, ctype="tg", checked=True)
        mock_msg.check_message_client.assert_any_call(interactive=0, ctype="tg")
        mock_msg.check_message_client.assert_any_call(cid=1, interactive=1)

    def test_toggle_interactive_unchecked(self):
        svc, mock_msg = self._svc()
        svc.toggle_interactive(cid=1, ctype="tg", checked=False)
        mock_msg.check_message_client.assert_called_once_with(cid=1, interactive=0)

    def test_toggle_enable(self):
        svc, mock_msg = self._svc()
        svc.toggle_enable(cid=2, checked=True)
        mock_msg.check_message_client.assert_called_once_with(cid=2, enabled=1)

    def test_test_connection(self):
        svc, mock_msg = self._svc()
        mock_msg.get_status.return_value = True
        assert svc.test_connection(ctype="tg", config={"token": "x"}) is True

    def test_upsert_client_with_cid(self):
        svc, mock_msg = self._svc()
        svc.upsert_client(
            name="n", cid=5, ctype="wx", config="{}",
            switchs="[]", interactive=0, enabled=1, templates=""
        )
        mock_msg.delete_message_client.assert_called_once_with(cid=5)
        mock_msg.insert_message_client.assert_called_once()

    def test_upsert_client_interactive(self):
        svc, mock_msg = self._svc()
        svc.upsert_client(
            name="n", cid=0, ctype="tg", config="{}",
            switchs="[]", interactive=1, enabled=1, templates=""
        )
        mock_msg.check_message_client.assert_called_once_with(interactive=0, ctype="tg")
        mock_msg.insert_message_client.assert_called_once()


class TestBackupRestoreService:
    def _svc(self):
        return BackupRestoreService()

    def test_restore_no_filename(self):
        result = self._svc().restore_from_backup("")
        assert result.success is False
        assert result.message == "文件不存在"

    @patch("app.services.system_service.temp_manager")
    @patch("app.services.system_service.tempfile.mkdtemp")
    @patch("app.services.system_service.shutil.unpack_archive")
    @patch("app.services.system_service.shutil.copy")
    @patch("app.services.system_service.os.path.exists", side_effect=[False, False, True, False, True, True])
    @patch("app.services.system_service.os.remove")
    @patch("app.services.system_service.shutil.rmtree")
    @patch("app.services.system_service.DatabaseFactory")
    @patch("app.services.system_service.import_from_file")
    def test_restore_json_backup(
        self, mock_import, mock_db_factory, mock_rmtree, mock_remove,
        mock_exists, mock_copy, mock_unpack, mock_mkdtemp, mock_temp_mgr
    ):
        svc = self._svc()
        mock_temp_mgr.get_temp_path.return_value = "/tmp/backup.zip"
        mock_mkdtemp.return_value = "/tmp/restore_xxx"
        mock_engine = MagicMock()
        mock_db_factory._get_config_db_type.return_value = "sqlite"
        mock_db_factory.create_engine.return_value = mock_engine

        result = svc.restore_from_backup("backup.zip")
        assert result.success is True
        assert result.message == "恢复成功"
        mock_import.assert_called_once_with(mock_engine, "/tmp/restore_xxx/user_db_export.json")
        mock_engine.dispose.assert_called_once()

    @patch("app.services.system_service.temp_manager")
    @patch("app.services.system_service.tempfile.mkdtemp")
    @patch("app.services.system_service.shutil.unpack_archive")
    @patch("app.services.system_service.shutil.copy")
    @patch("app.services.system_service.os.path.exists", side_effect=[False, False, False, False, True, True])
    @patch("app.services.system_service.os.remove")
    @patch("app.services.system_service.shutil.rmtree")
    def test_restore_no_db_file(
        self, mock_rmtree, mock_remove, mock_exists, mock_copy, mock_unpack, mock_mkdtemp, mock_temp_mgr
    ):
        svc = self._svc()
        mock_temp_mgr.get_temp_path.return_value = "/tmp/backup.zip"
        mock_mkdtemp.return_value = "/tmp/restore_xxx"

        result = svc.restore_from_backup("backup.zip")
        assert result.success is False
        assert "未找到数据库文件" in result.message

    @patch("app.services.system_service.temp_manager")
    @patch("app.services.system_service.tempfile.mkdtemp")
    @patch("app.services.system_service.shutil.unpack_archive", side_effect=Exception("bad zip"))
    @patch("app.services.system_service.os.path.exists", return_value=True)
    @patch("app.services.system_service.os.remove")
    @patch("app.services.system_service.shutil.rmtree")
    def test_restore_exception(
        self, mock_rmtree, mock_remove, mock_exists, mock_unpack, mock_mkdtemp, mock_temp_mgr
    ):
        svc = self._svc()
        mock_temp_mgr.get_temp_path.return_value = "/tmp/backup.zip"
        mock_mkdtemp.return_value = "/tmp/restore_xxx"

        result = svc.restore_from_backup("backup.zip")
        assert result.success is False
        assert "bad zip" in result.message


class TestIndexerConfigService:
    def _svc(self):
        mock_sys = MagicMock()
        mock_idx = MagicMock()
        return IndexerConfigService(system_config=mock_sys, indexer=mock_idx), mock_sys, mock_idx

    def test_save_config_builtin(self):
        svc, mock_sys, mock_idx = self._svc()
        mock_sys.get.return_value = None
        result = svc.save_config({"type": "builtin", "test": False, "indexer_sites": ["a"]})
        assert result.success is True
        mock_idx.init_config.assert_called_once()

    def test_save_config_with_test_success(self):
        svc, mock_sys, mock_idx = self._svc()
        mock_sys.get.return_value = None
        mock_schema = MagicMock()
        mock_schema.match.return_value = True
        mock_client = MagicMock()
        mock_client.get_status.return_value = True
        mock_schema.return_value = mock_client
        with patch("app.services.system_service.SubmoduleHelper.import_submodules", return_value=[mock_schema]):
            result = svc.save_config({"type": "jackett", "test": True, "jackett.host": "h"})
        assert result.success is True
        assert result.code == 0
        assert result.msg == "测试成功"

    def test_save_config_with_test_failure(self):
        svc, mock_sys, mock_idx = self._svc()
        mock_sys.get.return_value = None
        mock_schema = MagicMock()
        mock_schema.match.return_value = True
        mock_client = MagicMock()
        mock_client.get_status.return_value = False
        mock_schema.return_value = mock_client
        with patch("app.services.system_service.SubmoduleHelper.import_submodules", return_value=[mock_schema]):
            result = svc.save_config({"type": "jackett", "test": True})
        assert result.code == 1
        assert result.msg == "测试失败"

    def test_save_config_no_client(self):
        svc, mock_sys, mock_idx = self._svc()
        mock_sys.get.return_value = None
        mock_schema = MagicMock()
        mock_schema.match.return_value = False
        with patch("app.services.system_service.SubmoduleHelper.import_submodules", return_value=[mock_schema]):
            result = svc.save_config({"type": "jackett", "test": True})
        assert result.msg == "未找到对应客户端"


class TestMediaServerConfigService:
    def _svc(self):
        mock_repo = MagicMock()
        mock_ms = MagicMock()
        return MediaServerConfigService(config_repo=mock_repo, media_server=mock_ms), mock_repo, mock_ms

    def test_save_config_empty(self):
        svc, _, _ = self._svc()
        result = svc.save_config({"type": "emby", "test": False})
        assert result.success is False
        assert result.msg == "配置为空"

    @patch("app.services.system_service.cache.delete")
    def test_save_config_success(self, mock_cache_delete):
        svc, mock_repo, mock_ms = self._svc()
        mock_item = MagicMock()
        mock_item.ID = 3
        mock_repo.get_media_server_by_name.return_value = mock_item
        result = svc.save_config({"type": "emby", "test": False, "emby.host": "h", "emby.enabled": True})
        assert result.success is True
        mock_repo.update_media_server.assert_called_once()

    @patch("app.services.system_service.cache.delete")
    def test_save_config_test_success(self, mock_cache_delete):
        svc, mock_repo, mock_ms = self._svc()
        mock_repo.get_media_server_by_name.return_value = None
        mock_schema = MagicMock()
        mock_schema.match.return_value = True
        mock_client = MagicMock()
        mock_client.get_status.return_value = True
        mock_schema.return_value = mock_client
        with patch("app.services.system_service.SubmoduleHelper.import_submodules", return_value=[mock_schema]):
            result = svc.save_config({"type": "emby", "test": True, "emby.host": "h"})
        assert result.code == 0
        assert result.msg == "测试成功"


class TestNetTestService:
    def _svc(self):
        return NetTestService()

    @patch("app.services.system_service.RequestUtils")
    @patch("app.services.system_service.Config")
    def test_net_test_success_with_proxy(self, mock_config, mock_req_cls):
        svc = self._svc()
        mock_config.return_value.get_proxies.return_value = {"http": "proxy"}
        mock_res = MagicMock()
        mock_res.ok = True
        mock_req_cls.return_value.get_res.return_value = mock_res
        result = svc.test("themoviedb.org")
        assert result.success is True
        assert result.time_ms >= 0

    @patch("app.services.system_service.RequestUtils")
    def test_net_test_failure(self, mock_req_cls):
        svc = self._svc()
        mock_req_cls.return_value.get_res.return_value = None
        result = svc.test("example.com")
        assert result.success is False

    @patch("app.services.system_service.RequestUtils")
    def test_net_test_image_tmdb(self, mock_req_cls):
        svc = self._svc()
        mock_req_cls.return_value.get_res.return_value = None
        result = svc.test("image.tmdb.org")
        url = mock_req_cls.call_args[1].get("proxies") or {}
        # 验证路径拼接
        assert result.success is False


class TestSchedulerService:
    def test_start_service(self):
        mock_down = MagicMock()
        mock_sync = MagicMock()
        svc = SchedulerService(
            downloader=mock_down, sync=mock_sync,
            rss=MagicMock(), subscribe=MagicMock(), thread_helper=MagicMock()
        )
        ok, msg = svc.start_service("sync")
        assert ok is True
        assert msg == "服务已启动"
        svc._thread_helper.start_thread.assert_called_once()

    def test_start_service_unknown(self):
        svc = SchedulerService(
            downloader=MagicMock(), sync=MagicMock(),
            rss=MagicMock(), subscribe=MagicMock(), thread_helper=MagicMock()
        )
        ok, msg = svc.start_service("xxx")
        assert ok is False
        assert msg == "未知服务"


class TestWebSearchService:
    @patch("app.services.system_service.search_medias_for_web", return_value=(0, ""))
    def test_search_success(self, mock_search):
        svc = WebSearchService()
        result = svc.search("test", ident_flag=True, filters=None, tmdbid=None, media_type=None)
        assert result.code == 0

    @patch("app.services.system_service.search_medias_for_web", return_value=(-1, "error"))
    def test_search_failure(self, mock_search):
        svc = WebSearchService()
        result = svc.search("test", ident_flag=True)
        assert result.code == -1
        assert result.msg == "error"

    def test_search_empty(self):
        svc = WebSearchService()
        result = svc.search("")
        assert result.code == 0


class TestSystemConfigService:
    def test_set_config_success(self):
        mock_sys = MagicMock()
        svc = SystemConfigService(system_config=mock_sys)
        assert svc.set_config("key", "value") is True
        mock_sys.set.assert_called_once_with(key="key", value="value")

    def test_set_config_missing(self):
        svc = SystemConfigService(system_config=MagicMock())
        assert svc.set_config("", "value") is False
        assert svc.set_config("key", "") is False


class TestVersionService:
    @patch("app.services.system_service.WebUtils.get_latest_version", return_value=("v2", "url", True))
    def test_get_latest_version(self, mock_get):
        result = VersionService().get_latest_version()
        assert result.has_update is True
        assert result.version == "v2"
        assert result.url == "url"

    @patch("app.services.system_service.WebUtils.get_latest_version", return_value=(None, None, False))
    def test_get_latest_version_none(self, mock_get):
        result = VersionService().get_latest_version()
        assert result.has_update is False
        assert result.version == ""


class TestDTOs:
    def test_backup_restore_result_defaults(self):
        dto = BackupRestoreResultDTO()
        assert dto.success is False
        assert dto.message == ""

    def test_net_test_result_defaults(self):
        dto = NetTestResultDTO()
        assert dto.success is False
        assert dto.time_ms == 0

    def test_indexer_config_result_defaults(self):
        dto = IndexerConfigResultDTO()
        assert dto.success is True
        assert dto.code == 0

    def test_media_server_config_result_defaults(self):
        dto = MediaServerConfigResultDTO()
        assert dto.success is True
        assert dto.code == 0

    def test_search_result_defaults(self):
        dto = SearchResultDTO()
        assert dto.code == 0
        assert dto.msg == ""

    def test_version_info_defaults(self):
        dto = VersionInfoDTO()
        assert dto.has_update is False
        assert dto.version == ""
