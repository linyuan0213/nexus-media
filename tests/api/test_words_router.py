from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.deps import get_current_user, get_words_service
from api.main import app

client = TestClient(app)
app.dependency_overrides[get_current_user] = lambda: "testuser"


class TestWordsRouter:

    def _mock_words(self):
        mock_svc = MagicMock()
        app.dependency_overrides[get_words_service] = lambda: mock_svc
        return mock_svc

    def _teardown(self):
        app.dependency_overrides.pop(get_words_service, None)

    def test_add_custom_word_group_success(self):
        mock_svc = self._mock_words()
        mock_svc.add_word_group.return_value = (True, "添加成功")
        try:
            resp = client.post("/api/words/add_custom_word_group", json={
                "tmdb_id": 123,
                "tmdb_type": "tv"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "添加成功"
            mock_svc.add_word_group.assert_called_once_with(tmdb_id=123, tmdb_type="tv")
        finally:
            self._teardown()

    def test_add_custom_word_group_fail(self):
        mock_svc = self._mock_words()
        mock_svc.add_word_group.return_value = (False, "已存在")
        try:
            resp = client.post("/api/words/add_custom_word_group", json={
                "tmdb_id": 123,
                "tmdb_type": "tv"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "已存在"
        finally:
            self._teardown()

    def test_add_or_edit_custom_word_success(self):
        mock_svc = self._mock_words()
        mock_svc.add_or_edit_word.return_value = (True, "保存成功")
        try:
            resp = client.post("/api/words/add_or_edit_custom_word", json={
                "id": 1,
                "gid": 10,
                "group_type": "1",
                "new_replaced": "old",
                "new_replace": "new",
                "new_front": "",
                "new_back": "",
                "new_offset": "",
                "new_help": "",
                "type": "1",
                "season": None,
                "enabled": 1,
                "regex": 0,
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.add_or_edit_word.assert_called_once()
        finally:
            self._teardown()

    def test_analyse_import_custom_words_code(self):
        mock_svc = self._mock_words()
        g = MagicMock()
        g.id = "g1"
        g.name = "group1"
        g.link = "link1"
        g.type = 1
        g.seasons = "S01"
        g.words = {"w1": "v1"}
        mock_svc.analyse_import_code.return_value = ([g], "note text")
        try:
            resp = client.post("/api/words/analyse_import_custom_words_code", json={
                "import_code": "somecode"
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert data["groups"][0]["id"] == "g1"
            assert data["note_string"] == "note text"
        finally:
            self._teardown()

    def test_check_custom_words(self):
        mock_svc = self._mock_words()
        mock_svc.toggle_words.return_value = True
        try:
            resp = client.post("/api/words/check_custom_words", json={
                "ids_info": ["1", "2"],
                "flag": "enable"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.toggle_words.assert_called_once_with(ids_info=["1", "2"], flag="enable")
        finally:
            self._teardown()

    def test_check_custom_words_fail(self):
        mock_svc = self._mock_words()
        mock_svc.toggle_words.return_value = False
        try:
            resp = client.post("/api/words/check_custom_words", json={
                "ids_info": ["1"],
                "flag": "disable"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 1
            assert resp.json()["msg"] == "识别词状态设置失败"
        finally:
            self._teardown()

    def test_delete_custom_word_group(self):
        mock_svc = self._mock_words()
        mock_svc.delete_word_group.return_value = True
        try:
            resp = client.post("/api/words/delete_custom_word_group", json={"gid": 5})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_word_group.assert_called_once_with(5)
        finally:
            self._teardown()

    def test_delete_custom_words(self):
        mock_svc = self._mock_words()
        mock_svc.delete_words_by_ids.return_value = True
        try:
            resp = client.post("/api/words/delete_custom_words", json={
                "ids_info": ["1", "2"]
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            mock_svc.delete_words_by_ids.assert_called_once_with(["1", "2"])
        finally:
            self._teardown()

    def test_export_custom_words(self):
        mock_svc = self._mock_words()
        mock_svc.export_words.return_value = ("encoded_string", "note")
        try:
            resp = client.post("/api/words/export_custom_words", json={
                "ids_info": "1,2",
                "note": "my note"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["string"] == "encoded_string"
            mock_svc.export_words.assert_called_once_with(ids_info="1,2", note="my note")
        finally:
            self._teardown()

    def test_get_custom_word(self):
        mock_svc = self._mock_words()
        word = MagicMock()
        word.id = 1
        word.replaced = "old"
        word.replace = "new"
        word.front = "f"
        word.back = "b"
        word.offset = "o"
        word.type = 1
        word.group_id = 10
        word.season = -2
        word.enabled = 1
        word.regex = 0
        word.help = "h"
        mock_svc.get_word_by_id.return_value = word
        try:
            resp = client.post("/api/words/get_custom_word", json={"wid": 1})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["replaced"] == "old"
        finally:
            self._teardown()

    def test_get_custom_word_not_found(self):
        mock_svc = self._mock_words()
        mock_svc.get_word_by_id.return_value = None
        try:
            resp = client.post("/api/words/get_custom_word", json={"wid": 99})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"] == {}
        finally:
            self._teardown()

    def test_import_custom_words(self):
        mock_svc = self._mock_words()
        mock_svc.import_words.return_value = (True, "导入成功")
        try:
            resp = client.post("/api/words/import_custom_words", json={
                "import_code": "code",
                "ids_info": "1,2"
            })
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["msg"] == "导入成功"
        finally:
            self._teardown()

    @patch("api.routers.words.Category")
    def test_get_categories_movie(self, mock_cat_cls):
        cat = MagicMock()
        cat.movie_categorys = ["动作", "科幻"]
        cat.tv_categorys = []
        cat.anime_categorys = []
        mock_cat_cls.return_value = cat

        resp = client.post("/api/words/get_categories", json={
            "type": "电影",
            "id": "c1",
            "value": "v1"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["category"] == ["动作", "科幻"]

    @patch("api.routers.words.Category")
    def test_get_categories_tv(self, mock_cat_cls):
        cat = MagicMock()
        cat.movie_categorys = []
        cat.tv_categorys = ["剧情", "喜剧"]
        cat.anime_categorys = []
        mock_cat_cls.return_value = cat

        resp = client.post("/api/words/get_categories", json={
            "type": "电视剧"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["category"] == ["剧情", "喜剧"]

    @patch("api.routers.words.Category")
    def test_get_categories_anime(self, mock_cat_cls):
        cat = MagicMock()
        cat.movie_categorys = []
        cat.tv_categorys = []
        cat.anime_categorys = ["热血"]
        mock_cat_cls.return_value = cat

        resp = client.post("/api/words/get_categories", json={
            "type": "动漫"
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["category"] == ["热血"]

    def test_get_customwords(self):
        mock_svc = self._mock_words()
        mock_svc.get_all_word_groups.return_value = [{"id": 1, "title": "t"}]
        try:
            resp = client.post("/api/words/get_customwords", json={})
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["result"][0]["id"] == 1
        finally:
            self._teardown()
