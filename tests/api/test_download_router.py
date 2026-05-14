"""
测试 FastAPI Download Router
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.deps import (
    get_current_user,
    get_download_service,
    get_downloader_service,
    get_filetransfer_service,
    get_indexer_service,
    get_site_service,
)
from api.main import app

# 绕过认证
app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


class TestDownloadRouter:
    def _mock_download(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_download_service] = lambda: mock_svc
        return mock_svc

    def _teardown_download(self):
        app.dependency_overrides.pop(get_download_service, None)

    def _mock_downloader(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_downloader_service] = lambda: mock_svc
        return mock_svc

    def _teardown_downloader(self):
        app.dependency_overrides.pop(get_downloader_service, None)

    def _mock_site(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_site_service] = lambda: mock_svc
        return mock_svc

    def _teardown_site(self):
        app.dependency_overrides.pop(get_site_service, None)

    def _mock_indexer(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_indexer_service] = lambda: mock_svc
        return mock_svc

    def _teardown_indexer(self):
        app.dependency_overrides.pop(get_indexer_service, None)

    def _mock_ft(self):
        mock_ft = MagicMock()
        app.dependency_overrides[get_filetransfer_service] = lambda: mock_ft
        return mock_ft

    def _teardown_ft(self):
        app.dependency_overrides.pop(get_filetransfer_service, None)

    # ------------------------------------------------------------------
    # auto_remove_torrents
    # ------------------------------------------------------------------
    def test_auto_remove_torrents(self):
        mock_svc = self._mock_download()
        try:
            resp = client.post("/api/download/auto_remove_torrents", json={"tid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.auto_remove_torrents.assert_called_once_with(taskids="1")
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # check_downloader
    # ------------------------------------------------------------------
    def test_check_downloader(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/check_downloader", json={"did": "1", "flag": "enabled", "checked": True})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.check_downloader.assert_called_once_with(
                did="1", enabled=1, transfer=None, only_nastool=None, match_path=None
            )
        finally:
            self._teardown_downloader()

    def test_check_downloader_no_did(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/check_downloader", json={"flag": "enabled", "checked": True})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # del_downloader
    # ------------------------------------------------------------------
    def test_del_downloader(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/del_downloader", json={"did": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_downloader.assert_called_once_with(did="1")
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # delete_download_setting
    # ------------------------------------------------------------------
    def test_delete_download_setting(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/delete_download_setting", json={"sid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # delete_torrent_remove_task
    # ------------------------------------------------------------------
    def test_delete_torrent_remove_task(self):
        mock_svc = self._mock_download()
        mock_svc.delete_torrent_remove_task.return_value = True
        try:
            resp = client.post("/api/download/delete_torrent_remove_task", json={"tid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # download
    # ------------------------------------------------------------------
    def test_download(self):
        mock_svc = self._mock_download()
        mock_svc.download_from_search_results.return_value = MagicMock(success=True, message="下载成功")
        try:
            resp = client.post("/api/download/download", json={"id": 1, "dir": "/downloads", "setting": "default"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "下载成功"
            mock_svc.download_from_search_results.assert_called_once_with(
                dl_id=1, dl_dir="/downloads", dl_setting="default", user_name="testuser"
            )
        finally:
            self._teardown_download()

    def test_download_fail(self):
        mock_svc = self._mock_download()
        mock_svc.download_from_search_results.return_value = MagicMock(success=False, message="失败")
        try:
            resp = client.post("/api/download/download", json={"id": 1, "dir": "/downloads", "setting": "default"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
            assert resp.json()["msg"] == "失败"
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # download_link
    # ------------------------------------------------------------------
    def test_download_link(self):
        mock_svc = self._mock_download()
        mock_svc.download_from_link.return_value = MagicMock(success=True, message="下载成功")
        try:
            resp = client.post(
                "/api/download/download_link",
                json={
                    "site": "PT",
                    "enclosure": "https://x.torrent",
                    "title": "Test",
                    "description": "",
                    "page_url": "",
                    "size": "1G",
                    "seeders": "10",
                    "uploadvolumefactor": "1",
                    "downloadvolumefactor": "1",
                    "dl_dir": "/dl",
                    "dl_setting": "s1",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # download_torrent
    # ------------------------------------------------------------------
    def test_download_torrent(self):
        mock_svc = self._mock_download()
        mock_svc.download_from_torrent_files_or_urls.return_value = MagicMock(success=True, message="完成")
        try:
            resp = client.post(
                "/api/download/download_torrent", json={"files": [], "urls": ["magnet:?xt=urn"], "dl_dir": "/dl"}
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # get_download_dirs
    # ------------------------------------------------------------------
    def test_get_download_dirs(self):
        mock_site = self._mock_site()
        mock_site.get_site_download_setting.return_value = None
        mock_dl = self._mock_downloader()
        mock_dl.get_download_dirs.return_value = ["/downloads"]
        try:
            resp = client.post("/api/download/get_download_dirs", json={"sid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"] == ["/downloads"]
        finally:
            self._teardown_site()
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # get_download_setting
    # ------------------------------------------------------------------
    def test_get_download_setting(self):
        mock_svc = self._mock_downloader()
        mock_svc.get_download_setting.return_value = {"name": "default"}
        try:
            resp = client.post("/api/download/get_download_setting", json={"sid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"] == {"name": "default"}
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # get_downloaders
    # ------------------------------------------------------------------
    def test_get_downloaders(self):
        mock_svc = self._mock_downloader()
        mock_svc.get_downloader_conf.return_value = {"id": "1"}
        try:
            resp = client.post("/api/download/get_downloaders", json={"did": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"] == {"id": "1"}
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # get_indexer_statistics
    # ------------------------------------------------------------------
    def test_get_indexer_statistics(self):
        mock_svc = self._mock_download()
        dto = MagicMock()
        dto.name = "idx"
        dto.total = 10
        dto.fail = 1
        dto.success = 9
        dto.avg = 0.5
        mock_svc.get_indexer_statistics.return_value = ([dto], [])
        try:
            resp = client.post("/api/download/get_indexer_statistics", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["name"] == "idx"
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # get_indexers
    # ------------------------------------------------------------------
    def test_get_indexers(self):
        mock_svc = self._mock_indexer()
        indexer = MagicMock()
        indexer.id = "1"
        indexer.name = "BuiltIn"
        mock_svc.get_user_indexers.return_value = [indexer]
        try:
            resp = client.post("/api/download/get_indexers", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["name"] == "BuiltIn"
        finally:
            self._teardown_indexer()

    # ------------------------------------------------------------------
    # get_remove_torrents
    # ------------------------------------------------------------------
    def test_get_remove_torrents(self):
        mock_svc = self._mock_download()
        mock_svc.get_remove_torrents.return_value = (True, [{"id": "1"}])
        try:
            resp = client.post("/api/download/get_remove_torrents", json={"tid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["id"] == "1"
        finally:
            self._teardown_download()

    def test_get_remove_torrents_empty(self):
        mock_svc = self._mock_download()
        mock_svc.get_remove_torrents.return_value = (False, [])
        try:
            resp = client.post("/api/download/get_remove_torrents", json={"tid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # get_torrent_remove_task
    # ------------------------------------------------------------------
    def test_get_torrent_remove_task(self):
        mock_svc = self._mock_download()
        mock_svc.get_torrent_remove_tasks.return_value = [{"id": "1"}]
        try:
            resp = client.post("/api/download/get_torrent_remove_task", json={"tid": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # pt_info / pt_remove / pt_start / pt_stop
    # ------------------------------------------------------------------
    def test_pt_info(self):
        mock_svc = self._mock_downloader()
        mock_svc.get_downloading_progress.return_value = [{"id": "1"}]
        try:
            resp = client.post("/api/download/pt_info", json={"ids": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"][0]["id"] == "1"
        finally:
            self._teardown_downloader()

    def test_pt_remove(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/pt_remove", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_torrents.assert_called_once_with(ids="1", delete_file=True)
        finally:
            self._teardown_downloader()

    def test_pt_start(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/pt_start", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.start_torrents.assert_called_once_with(ids="1")
        finally:
            self._teardown_downloader()

    def test_pt_stop(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post("/api/download/pt_stop", json={"id": "1"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.stop_torrents.assert_called_once_with(ids="1")
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # test_downloader
    # ------------------------------------------------------------------
    def test_test_downloader(self):
        mock_svc = self._mock_downloader()
        mock_svc.get_status.return_value = True
        try:
            resp = client.post("/api/download/test_downloader", json={"type": "qb", "config": "{}"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # update_download_setting
    # ------------------------------------------------------------------
    def test_update_download_setting(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post(
                "/api/download/update_download_setting", json={"sid": "1", "name": "default", "category": "movie"}
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # update_downloader
    # ------------------------------------------------------------------
    def test_update_downloader(self):
        mock_svc = self._mock_downloader()
        try:
            resp = client.post(
                "/api/download/update_downloader",
                json={"did": "1", "name": "qb", "type": "qbittorrent", "config": "{}", "download_dir": "[]"},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_downloader()

    # ------------------------------------------------------------------
    # update_torrent_remove_task
    # ------------------------------------------------------------------
    def test_update_torrent_remove_task(self):
        mock_svc = self._mock_download()
        mock_svc.update_torrent_remove_task.return_value = (True, "")
        try:
            resp = client.post("/api/download/update_torrent_remove_task", json={"data": {"name": "task1"}})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # get_downloading
    # ------------------------------------------------------------------
    def test_get_downloading(self):
        mock_svc = self._mock_download()
        mock_svc.get_downloading_with_media_info.return_value = [{"title": "Movie"}]
        try:
            resp = client.post("/api/download/get_downloading", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["title"] == "Movie"
        finally:
            self._teardown_download()

    # ------------------------------------------------------------------
    # truncate_blacklist
    # ------------------------------------------------------------------
    def test_truncate_blacklist(self):
        mock_ft = self._mock_ft()
        try:
            resp = client.post("/api/download/truncate_blacklist", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_ft.truncate_transfer_blacklist.assert_called_once()
        finally:
            self._teardown_ft()
