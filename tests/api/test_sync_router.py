"""
测试 FastAPI Sync Router
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import (
    get_current_user,
    get_filetransfer_service,
    get_sync_service,
    get_thread_helper,
)
from api.main import app

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestSyncRouter:
    def _mock_sync(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_sync_service] = lambda: mock_svc
        return mock_svc

    def _teardown_sync(self):
        app.dependency_overrides.pop(get_sync_service, None)

    def _mock_ft(self):
        mock_ft = MagicMock()
        app.dependency_overrides[get_filetransfer_service] = lambda: mock_ft
        return mock_ft

    def _teardown_ft(self):
        app.dependency_overrides.pop(get_filetransfer_service, None)

    def _mock_thread(self):
        mock_th = MagicMock()
        app.dependency_overrides[get_thread_helper] = lambda: mock_th
        return mock_th

    def _teardown_thread(self):
        app.dependency_overrides.pop(get_thread_helper, None)

    # ------------------------------------------------------------------
    # add_or_edit_sync_path
    # ------------------------------------------------------------------
    def test_add_or_edit_sync_path(self):
        mock_svc = self._mock_sync()
        mock_svc.add_or_edit_sync_path.return_value = (True, "保存成功")
        try:
            resp = client.post(
                "/api/sync/add_or_edit_sync_path",
                json={
                    "sid": 1,
                    "source": "/src",
                    "dest": "/dst",
                    "mode": "copy",
                    "compatibility": 1,
                    "rename": 1,
                    "enabled": 1,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    def test_add_or_edit_sync_path_fail(self):
        mock_svc = self._mock_sync()
        mock_svc.add_or_edit_sync_path.return_value = (False, "目录不存在")
        try:
            resp = client.post("/api/sync/add_or_edit_sync_path", json={"source": "/nonexist"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # check_sync_path
    # ------------------------------------------------------------------
    def test_check_sync_path(self):
        mock_svc = self._mock_sync()
        mock_svc.check_sync_path.return_value = (True, "")
        try:
            resp = client.post("/api/sync/check_sync_path", json={"sid": 1, "flag": "enabled", "checked": True})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    def test_check_sync_path_fail(self):
        mock_svc = self._mock_sync()
        mock_svc.check_sync_path.return_value = (False, "")
        try:
            resp = client.post("/api/sync/check_sync_path", json={"sid": 1, "flag": "enabled", "checked": False})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # del_unknown_path
    # ------------------------------------------------------------------
    def test_del_unknown_path_single(self):
        mock_ft = self._mock_ft()
        mock_ft.delete_transfer_unknown.return_value = 0
        try:
            resp = client.post("/api/sync/del_unknown_path", json={"id": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_ft()

    def test_del_unknown_path_list(self):
        self._mock_ft()
        try:
            resp = client.post("/api/sync/del_unknown_path", json={"id": [1, 2]})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_ft()

    # ------------------------------------------------------------------
    # delete_files
    # ------------------------------------------------------------------
    def test_delete_files(self):
        mock_ft = self._mock_ft()
        mock_ft.delete_media_file.return_value = (True, "deleted")
        try:
            resp = client.post("/api/sync/delete_files", json={"files": ["/path/to/file.mkv"]})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_ft()

    # ------------------------------------------------------------------
    # delete_sync_path
    # ------------------------------------------------------------------
    def test_delete_sync_path(self):
        mock_svc = self._mock_sync()
        try:
            resp = client.post("/api/sync/delete_sync_path", json={"sid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_sync_path.assert_called_once_with(1)
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # get_sub_path
    # ------------------------------------------------------------------
    def test_get_sub_path(self):
        mock_svc = self._mock_sync()
        mock_svc.get_sub_path.return_value = [{"path": "/a", "name": "a", "type": "dir"}]
        try:
            resp = client.post("/api/sync/get_sub_path", json={"directory": "/", "filter": "ALL"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["count"] == 1
        finally:
            self._teardown_sync()

    def test_get_sub_path_exception(self):
        mock_svc = self._mock_sync()
        mock_svc.get_sub_path.side_effect = Exception("disk error")
        try:
            resp = client.post("/api/sync/get_sub_path", json={"directory": "/bad"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # rename
    # ------------------------------------------------------------------
    def test_rename_with_logid(self):
        mock_svc = self._mock_sync()
        dto = MagicMock()
        dto.SOURCE_PATH = "/src"
        dto.SOURCE_FILENAME = "file.mkv"
        dto.DEST = "/dst"
        mock_svc.get_transfer_info_by_id.return_value = dto
        mock_svc.manual_transfer.return_value = MagicMock(success=True, message="ok")
        self._mock_ft()
        try:
            resp = client.post("/api/sync/rename", json={"logid": 1, "syncmod": "copy", "tmdb": 123, "type": "MOV"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "转移成功"
        finally:
            self._teardown_sync()
            self._teardown_ft()

    def test_rename_logid_not_found(self):
        mock_svc = self._mock_sync()
        self._mock_ft()
        mock_svc.get_transfer_info_by_id.return_value = None
        try:
            resp = client.post("/api/sync/rename", json={"logid": 99})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_sync()
            self._teardown_ft()

    def test_rename_unknown_id_not_found(self):
        mock_svc = self._mock_sync()
        self._mock_ft()
        mock_svc.get_transfer_info_by_id.return_value = None
        mock_svc.get_unknown_info_by_id.return_value = None
        try:
            resp = client.post("/api/sync/rename", json={"unknown_id": 99})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_sync()
            self._teardown_ft()

    def test_rename_no_path(self):
        mock_svc = self._mock_sync()
        self._mock_ft()
        mock_svc.get_transfer_info_by_id.return_value = None
        mock_svc.get_unknown_info_by_id.return_value = None
        try:
            resp = client.post("/api/sync/rename", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
            assert resp.json()["msg"] == "输入路径有误"
        finally:
            self._teardown_sync()
            self._teardown_ft()

    def test_rename_fail(self):
        mock_svc = self._mock_sync()
        dto = MagicMock()
        dto.SOURCE_PATH = "/src"
        dto.SOURCE_FILENAME = "file.mkv"
        dto.DEST = "/dst"
        mock_svc.get_transfer_info_by_id.return_value = dto
        mock_svc.manual_transfer.return_value = MagicMock(success=False, message="failed")
        self._mock_ft()
        try:
            resp = client.post("/api/sync/rename", json={"logid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 2
        finally:
            self._teardown_sync()
            self._teardown_ft()

    # ------------------------------------------------------------------
    # rename_file
    # ------------------------------------------------------------------
    def test_rename_file(self):
        mock_svc = self._mock_sync()
        mock_svc.rename_file.return_value = MagicMock(success=True, message="")
        try:
            resp = client.post("/api/sync/rename_file", json={"path": "/old", "name": "new.mkv"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    def test_rename_file_fail(self):
        mock_svc = self._mock_sync()
        mock_svc.rename_file.return_value = MagicMock(success=False, message="err")
        try:
            resp = client.post("/api/sync/rename_file", json={"path": "/old", "name": "new.mkv"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # rename_udf
    # ------------------------------------------------------------------
    @patch("api.routers.sync.os.path.exists", return_value=True)
    def test_rename_udf(self, mock_exists):
        mock_svc = self._mock_sync()
        mock_svc.manual_transfer.return_value = MagicMock(success=True, message="ok")
        try:
            resp = client.post(
                "/api/sync/rename_udf", json={"inpath": "/in", "outpath": "/out", "syncmod": "copy", "type": "MOV"}
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    @patch("api.routers.sync.os.path.exists", return_value=False)
    def test_rename_udf_path_not_exist(self, mock_exists):
        self._mock_sync()
        try:
            resp = client.post("/api/sync/rename_udf", json={"inpath": "/nonexist"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
            assert resp.json()["msg"] == "输入路径不存在"
        finally:
            self._teardown_sync()

    @patch("api.routers.sync.os.path.exists", return_value=True)
    def test_rename_udf_fail(self, mock_exists):
        mock_svc = self._mock_sync()
        mock_svc.manual_transfer.return_value = MagicMock(success=False, message="bad")
        try:
            resp = client.post("/api/sync/rename_udf", json={"inpath": "/in", "syncmod": "copy"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 2
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # run_directory_sync
    # ------------------------------------------------------------------
    def test_run_directory_sync(self):
        self._mock_sync()
        mock_th = self._mock_thread()
        try:
            resp = client.post("/api/sync/run_directory_sync", json={"sid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_th.start_thread.assert_called_once()
        finally:
            self._teardown_sync()
            self._teardown_thread()

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------
    def test_test_connection(self):
        mock_svc = self._mock_sync()
        mock_svc.test_connection.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/sync/test_connection", json={"command": "Config().get_config()"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    def test_test_connection_fail(self):
        mock_svc = self._mock_sync()
        mock_svc.test_connection.return_value = MagicMock(success=False)
        try:
            resp = client.post("/api/sync/test_connection", json={"command": "BadCmd()"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # update_directory
    # ------------------------------------------------------------------
    def test_update_directory(self):
        mock_svc = self._mock_sync()
        mock_svc.update_directory.return_value = MagicMock(success=True)
        try:
            resp = client.post("/api/sync/update_directory", json={"oper": "add", "key": "dir", "value": "/new"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    def test_update_directory_fail(self):
        mock_svc = self._mock_sync()
        mock_svc.update_directory.return_value = MagicMock(success=False)
        try:
            resp = client.post("/api/sync/update_directory", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # delete_history
    # ------------------------------------------------------------------
    def test_delete_history(self):
        mock_ft = self._mock_ft()
        try:
            resp = client.post("/api/sync/delete_history", json={"logids": [1, 2], "flag": "hist"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_ft.delete_history.assert_called_once_with(logids=[1, 2], flag="hist")
        finally:
            self._teardown_ft()

    # ------------------------------------------------------------------
    # get_sync_path
    # ------------------------------------------------------------------
    def test_get_sync_path(self):
        mock_svc = self._mock_sync()
        mock_svc.get_sync_paths.return_value = [{"id": 1, "source": "/src"}]
        try:
            resp = client.post("/api/sync/get_sync_path", json={"sid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["id"] == 1
        finally:
            self._teardown_sync()

    def test_get_sync_path_no_sid(self):
        mock_svc = self._mock_sync()
        mock_svc.get_sync_paths.return_value = []
        try:
            resp = client.post("/api/sync/get_sync_path", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_sync()

    # ------------------------------------------------------------------
    # re_identification
    # ------------------------------------------------------------------
    def test_re_identification(self):
        mock_svc = self._mock_sync()
        mock_svc.re_identify_items.return_value = MagicMock(success=True, message="转移成功")
        try:
            resp = client.post("/api/sync/re_identification", json={"flag": "history", "ids": [1, 2]})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "转移成功"
        finally:
            self._teardown_sync()

    def test_re_identification_fail(self):
        mock_svc = self._mock_sync()
        mock_svc.re_identify_items.return_value = MagicMock(success=False, message="失败")
        try:
            resp = client.post("/api/sync/re_identification", json={"flag": "unidentification", "ids": [1]})
            assert resp.status_code == 200
            assert resp.json()["code"] == 2
        finally:
            self._teardown_sync()
