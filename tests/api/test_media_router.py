# -*- coding: utf-8 -*-
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.deps import (
    get_current_user,
    get_downloader_service,
    get_media_file_service,
    get_media_info_service,
    get_media_library_service,
    get_media_recommendation_service,
    get_searcher_service,
    get_search_result_service,
    get_transfer_history_service,
)
from api.main import app

client = TestClient(app)
app.dependency_overrides[get_current_user] = lambda: "testuser"


class TestMediaRouter:

    # ----- MediaFileService -----

    def _mock_media_file(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_media_file_service] = lambda: mock_svc
        return mock_svc

    def _teardown_media_file(self):
        app.dependency_overrides.pop(get_media_file_service, None)

    def test_download_subtitle_success(self):
        mock_svc = self._mock_media_file()
        mock_svc.download_subtitle.return_value = (True, "下载成功")
        try:
            resp = client.post("/api/media/download_subtitle", json={
                "path": "/movie", "name": "test.mkv"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "下载成功"
        finally:
            self._teardown_media_file()

    def test_download_subtitle_fail(self):
        mock_svc = self._mock_media_file()
        mock_svc.download_subtitle.return_value = (False, "失败")
        try:
            resp = client.post("/api/media/download_subtitle", json={
                "path": "/movie", "name": "test.mkv"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_media_file()

    def test_media_path_scrap_success(self):
        mock_svc = self._mock_media_file()
        mock_svc.scrap_media_path.return_value = "刮削完成"
        try:
            resp = client.post("/api/media/media_path_scrap", json={"path": "/movie"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_media_file()

    def test_media_path_scrap_fail(self):
        mock_svc = self._mock_media_file()
        mock_svc.scrap_media_path.return_value = "请配置媒体库"
        try:
            resp = client.post("/api/media/media_path_scrap", json={"path": "/movie"})
            assert resp.status_code == 200
            assert resp.json()["code"] == -1
        finally:
            self._teardown_media_file()

    def test_save_user_script(self):
        mock_svc = self._mock_media_file()
        try:
            resp = client.post("/api/media/save_user_script", json={
                "javascript": "alert(1)", "css": "body{}"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.save_user_script.assert_called_once_with(script="alert(1)", css="body{}")
        finally:
            self._teardown_media_file()

    def test_get_category_config(self):
        mock_svc = self._mock_media_file()
        mock_svc.get_category_config.return_value = (True, "config text")
        try:
            resp = client.post("/api/media/get_category_config", json={
                "category_name": "movie"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["text"] == "config text"
        finally:
            self._teardown_media_file()

    def test_update_category_config(self):
        mock_svc = self._mock_media_file()
        mock_svc.update_category_config.return_value = "保存成功"
        try:
            resp = client.post("/api/media/update_category_config", json={
                "config": "new config"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_media_file()

    # ----- MediaInfoService -----

    def _mock_media_info(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_media_info_service] = lambda: mock_svc
        return mock_svc

    def _teardown_media_info(self):
        app.dependency_overrides.pop(get_media_info_service, None)

    def test_get_season_episodes(self):
        mock_svc = self._mock_media_info()
        result = MagicMock()
        result.episodes = [{"episode": 1}]
        mock_svc.get_season_episodes.return_value = result
        try:
            resp = client.post("/api/media/get_season_episodes", json={
                "tmdbid": 123, "title": "t", "year": "2023", "season": 1
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["episodes"][0]["episode"] == 1
        finally:
            self._teardown_media_info()

    def test_get_tvseason_list(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_tvseason_list.return_value = [{"season": 1}]
        try:
            resp = client.post("/api/media/get_tvseason_list", json={
                "tmdbid": 123, "title": "t"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["seasons"][0]["season"] == 1
        finally:
            self._teardown_media_info()

    def test_media_info(self):
        mock_svc = self._mock_media_info()
        result = MagicMock()
        result.type = "MOV"
        result.type_str = "电影"
        result.page = None
        result.title = "Test"
        result.vote_average = 8.0
        result.poster_path = "/p.jpg"
        result.release_date = "2023-01-01"
        result.year = "2023"
        result.overview = "desc"
        result.link_url = "url"
        result.tmdbid = 123
        result.rssid = None
        result.seasons = None
        mock_svc.get_media_info_detail.return_value = result
        try:
            resp = client.post("/api/media/media_info", json={
                "id": "123", "type": "MOV", "title": "Test"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["title"] == "Test"
        finally:
            self._teardown_media_info()

    def test_media_person(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_media_person.return_value = {"name": "actor"}
        try:
            resp = client.post("/api/media/media_person", json={
                "tmdbid": 123, "type": "MOV", "keyword": None
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["name"] == "actor"
        finally:
            self._teardown_media_info()

    def test_media_person_no_params(self):
        mock_svc = self._mock_media_info()
        try:
            resp = client.post("/api/media/media_person", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
        finally:
            self._teardown_media_info()

    def test_media_recommendations(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_media_recommendations.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/media/media_recommendations", json={
                "tmdbid": 123, "type": "MOV", "page": 1
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_media_info()

    def test_media_similar(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_media_similar.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/media/media_similar", json={
                "tmdbid": 123, "type": "MOV", "page": 1
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_media_info()

    def test_movie_calendar_data(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_movie_calendar.return_value = {"date": "2023-01-01"}
        try:
            resp = client.post("/api/media/movie_calendar_data", json={
                "id": "123", "rssid": "r1"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["date"] == "2023-01-01"
        finally:
            self._teardown_media_info()

    def test_name_test(self):
        mock_svc = self._mock_media_info()
        mock_svc.name_test.return_value = {"name": "test"}
        try:
            resp = client.post("/api/media/name_test", json={
                "name": "Test Movie", "subtitle": ""
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["name"] == "test"
        finally:
            self._teardown_media_info()

    def test_person_medias(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_person_medias.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/media/person_medias", json={
                "personid": 123, "type": "MOV", "page": 1
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_media_info()

    def test_tv_calendar_data(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_tv_calendar.return_value = [{"date": "2023-01-01"}]
        try:
            resp = client.post("/api/media/tv_calendar_data", json={
                "id": "123", "season": 1, "name": "Test", "rssid": "r1"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["events"][0]["date"] == "2023-01-01"
        finally:
            self._teardown_media_info()

    def test_media_detail(self):
        mock_svc = self._mock_media_info()
        mock_svc.get_media_detail.return_value = {"title": "Test"}
        try:
            resp = client.post("/api/media/media_detail", json={
                "tmdbid": 123, "type": "MOV"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["title"] == "Test"
        finally:
            self._teardown_media_info()

    def test_search_media_infos(self):
        mock_svc = self._mock_media_info()
        mock_svc.search_media_infos.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/media/search_media_infos", json={
                "keyword": "test", "searchtype": "tmdb"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["id"] == 1
        finally:
            self._teardown_media_info()

    # ----- MediaLibraryService -----

    def _mock_media_library(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_media_library_service] = lambda: mock_svc
        return mock_svc

    def _teardown_media_library(self):
        app.dependency_overrides.pop(get_media_library_service, None)

    def test_mediasync_state(self):
        mock_svc = self._mock_media_library()
        mock_svc.get_sync_state.return_value = "同步中"
        try:
            resp = client.post("/api/media/mediasync_state", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["text"] == "同步中"
        finally:
            self._teardown_media_library()

    def test_start_mediasync(self):
        mock_svc = self._mock_media_library()
        try:
            resp = client.post("/api/media/start_mediasync", json={
                "librarys": ["lib1"]
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.start_sync.assert_called_once_with(librarys=["lib1"])
        finally:
            self._teardown_media_library()

    def test_get_library_mediacount(self):
        mock_svc = self._mock_media_library()
        mock_svc.get_media_count.return_value = {"movie": 10}
        try:
            resp = client.post("/api/media/get_library_mediacount", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["movie"] == 10
        finally:
            self._teardown_media_library()

    def test_get_library_playhistory(self):
        mock_svc = self._mock_media_library()
        mock_svc.get_play_history.return_value = [{"title": "t"}]
        try:
            resp = client.post("/api/media/get_library_playhistory", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["title"] == "t"
        finally:
            self._teardown_media_library()

    def test_get_library_spacesize(self):
        mock_svc = self._mock_media_library()
        result = MagicMock()
        result.used_percent = 50
        result.free_space = "100G"
        result.used_space = "100G"
        result.total_space = "200G"
        mock_svc.get_space_info.return_value = result
        try:
            resp = client.post("/api/media/get_library_spacesize", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["UsedPercent"] == 50
        finally:
            self._teardown_media_library()

    # ----- TransferHistoryService -----

    def _mock_transfer_history(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_transfer_history_service] = lambda: mock_svc
        return mock_svc

    def _teardown_transfer_history(self):
        app.dependency_overrides.pop(get_transfer_history_service, None)

    def test_clear_history(self):
        mock_svc = self._mock_transfer_history()
        try:
            resp = client.post("/api/media/clear_history", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.clear_history.assert_called_once()
        finally:
            self._teardown_transfer_history()

    def test_get_transfer_history(self):
        mock_svc = self._mock_transfer_history()
        result = MagicMock()
        result.total = 10
        result.result = []
        result.total_page = 1
        result.page_num = 30
        result.current_page = 1
        mock_svc.get_transfer_history_page.return_value = result
        try:
            resp = client.post("/api/media/get_transfer_history", json={
                "keyword": "", "page": 1, "pagenum": 30
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["total"] == 10
        finally:
            self._teardown_transfer_history()

    def test_get_transfer_statistics(self):
        mock_svc = self._mock_transfer_history()
        mock_svc.get_transfer_statistics.return_value = {"count": 5}
        try:
            resp = client.post("/api/media/get_transfer_statistics", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["count"] == 5
        finally:
            self._teardown_transfer_history()

    def test_get_unknown_list(self):
        mock_svc = self._mock_transfer_history()
        mock_svc.get_unknown_list.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/media/get_unknown_list", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["items"][0]["id"] == 1
        finally:
            self._teardown_transfer_history()

    def test_get_unknown_list_by_page(self):
        mock_svc = self._mock_transfer_history()
        result = MagicMock()
        result.total = 5
        result.items = []
        result.total_page = 1
        result.page_num = 30
        result.current_page = 1
        mock_svc.get_unknown_list_by_page.return_value = result
        try:
            resp = client.post("/api/media/get_unknown_list_by_page", json={
                "keyword": "", "page": 1, "pagenum": 30
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["total"] == 5
        finally:
            self._teardown_transfer_history()

    def test_unidentification(self):
        mock_svc = self._mock_transfer_history()
        mock_svc.re_identify_unknown.return_value = 3
        try:
            resp = client.post("/api/media/unidentification", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            self._teardown_transfer_history()

    # ----- Downloader -----

    def _mock_downloader(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_downloader_service] = lambda: mock_svc
        return mock_svc

    def _teardown_downloader(self):
        app.dependency_overrides.pop(get_downloader_service, None)

    def test_get_downloaded(self):
        mock_svc = self._mock_downloader()
        item = MagicMock()
        item.TMDBID = 123
        item.TITLE = "Test"
        item.TYPE = "电影"
        item.YEAR = "2023"
        item.VOTE = 8.0
        item.POSTER = "/p.jpg"
        item.TORRENT = "desc"
        item.DATE = "2023-01-01"
        item.SITE = "site"
        mock_svc.get_download_history.return_value = [item]
        try:
            resp = client.post("/api/media/get_downloaded", json={"page": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["Items"][0]["title"] == "Test"
        finally:
            self._teardown_downloader()

    # ----- Searcher / SearchResultService -----

    def _mock_searcher(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_searcher_service] = lambda: mock_svc
        return mock_svc

    def _teardown_searcher(self):
        app.dependency_overrides.pop(get_searcher_service, None)

    def _mock_search_result(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_search_result_service] = lambda: mock_svc
        return mock_svc

    def _teardown_search_result(self):
        app.dependency_overrides.pop(get_search_result_service, None)

    def test_get_search_result(self):
        searcher = self._mock_searcher()
        searcher.get_search_results.return_value = []
        result_svc = self._mock_search_result()
        result = MagicMock()
        result.total = 10
        result.result = {}
        result_svc.group_search_results.return_value = result
        try:
            resp = client.post("/api/media/get_search_result", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["total"] == 10
        finally:
            self._teardown_searcher()
            self._teardown_search_result()

    # ----- MediaRecommendationService -----

    def _mock_media_recommendation(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_media_recommendation_service] = lambda: mock_svc
        return mock_svc

    def _teardown_media_recommendation(self):
        app.dependency_overrides.pop(get_media_recommendation_service, None)

    def test_get_recommend(self):
        mock_svc = self._mock_media_recommendation()
        mock_svc.get_recommend_items.return_value = [{"id": 1}]
        try:
            resp = client.post("/api/media/get_recommend", json={"type": "movie"})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["Items"][0]["id"] == 1
        finally:
            self._teardown_media_recommendation()

    def test_get_recommend_with_data_wrapper(self):
        mock_svc = self._mock_media_recommendation()
        mock_svc.get_recommend_items.return_value = [{"id": 2}]
        try:
            resp = client.post("/api/media/get_recommend", json={
                "data": {"type": "MOV", "subtype": "hm", "page": 1}
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["Items"][0]["id"] == 2
            mock_svc.get_recommend_items.assert_called_once_with(
                {"type": "MOV", "subtype": "hm", "page": 1})
        finally:
            self._teardown_media_recommendation()
