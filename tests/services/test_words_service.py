# -*- coding: utf-8 -*-
"""
WordsService 单元测试
"""
import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.words import (
    WordDTO,
    WordGroupExportDTO,
)
from app.services.words_service import WordsService


class FakeWordRow:
    """模拟 WordRepository 返回的行对象"""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_words_helper():
    return MagicMock()


@pytest.fixture
def mock_media():
    return MagicMock()


@pytest.fixture
def svc(mock_words_helper, mock_media):
    return WordsService(words_helper=mock_words_helper, media=mock_media)


class TestValidateOffset:
    def test_valid_offset(self, svc):
        assert svc._validate_offset("3", "EP+1") is None
        assert svc._validate_offset("4", "EP-1") is None

    def test_invalid_no_ep(self, svc):
        assert svc._validate_offset("3", "1+1") == "偏移集数格式有误"

    def test_invalid_chars(self, svc):
        assert svc._validate_offset("3", "EP+abc") == "偏移集数格式有误"

    def test_non_offset_type(self, svc):
        assert svc._validate_offset("1", "") is None


class TestAddWordGroup:
    def test_add_tv_group_success(self, svc, mock_words_helper, mock_media):
        mock_words_helper.is_custom_word_group_existed.return_value = False
        mock_media.get_tmdb_info.return_value = {
            "name": "Test TV",
            "first_air_date": "2020-01-01",
            "number_of_seasons": 2
        }
        ok, msg = svc.add_word_group(123, "tv")
        assert ok is True
        mock_words_helper.insert_custom_word_groups.assert_called_once()

    def test_add_tv_group_already_exists(self, svc, mock_words_helper):
        mock_words_helper.is_custom_word_group_existed.return_value = True
        ok, msg = svc.add_word_group(123, "tv")
        assert ok is False
        assert "已存在" in msg

    def test_add_movie_group_tmdb_not_found(self, svc, mock_words_helper, mock_media):
        mock_words_helper.is_custom_word_group_existed.return_value = False
        mock_media.get_tmdb_info.return_value = None
        ok, msg = svc.add_word_group(123, "movie")
        assert ok is False
        assert "无法查询到TMDB信息" in msg

    def test_add_invalid_type(self, svc):
        ok, msg = svc.add_word_group(123, "invalid")
        assert ok is False
        assert "无法识别" in msg


class TestAddOrEditWord:
    def test_add_block_word(self, svc, mock_words_helper):
        mock_words_helper.is_custom_words_existed.return_value = False
        ok, msg = svc.add_or_edit_word(
            wid=None, gid=1, group_type="1",
            replaced="bad", replace="", front="", back="", offset="",
            whelp="", wtype="1", season=-2, enabled=1, regex=0
        )
        assert ok is True
        mock_words_helper.insert_custom_word.assert_called_once()

    def test_add_replace_word_exists(self, svc, mock_words_helper):
        mock_words_helper.is_custom_words_existed.return_value = True
        ok, msg = svc.add_or_edit_word(
            wid=None, gid=1, group_type="1",
            replaced="old", replace="new", front="", back="", offset="",
            whelp="", wtype="2", season=-2, enabled=1, regex=0
        )
        assert ok is False
        assert "已存在" in msg

    def test_add_offset_word_invalid_format(self, svc):
        ok, msg = svc.add_or_edit_word(
            wid=None, gid=1, group_type="1",
            replaced="", replace="", front="ep", back="end", offset="abc",
            whelp="", wtype="4", season=-2, enabled=1, regex=0
        )
        assert ok is False
        assert "偏移集数格式有误" in msg

    def test_edit_word_deletes_old(self, svc, mock_words_helper):
        mock_words_helper.is_custom_words_existed.return_value = False
        ok, msg = svc.add_or_edit_word(
            wid=5, gid=1, group_type="1",
            replaced="x", replace="", front="", back="", offset="",
            whelp="", wtype="1", season=-2, enabled=1, regex=0
        )
        assert ok is True
        mock_words_helper.delete_custom_word.assert_called_once_with(wid=5)


class TestDeleteOperations:
    def test_delete_word(self, svc, mock_words_helper):
        svc.delete_word(wid=10)
        mock_words_helper.delete_custom_word.assert_called_once_with(wid=10)

    def test_delete_words_by_ids(self, svc, mock_words_helper):
        svc.delete_words_by_ids(["g_1", "g_2"])
        assert mock_words_helper.delete_custom_word.call_count == 2

    def test_delete_words_all(self, svc, mock_words_helper):
        svc.delete_words_by_ids([])
        mock_words_helper.delete_custom_word.assert_called_once_with()

    def test_delete_word_group(self, svc, mock_words_helper):
        svc.delete_word_group(gid=3)
        mock_words_helper.delete_custom_word_group.assert_called_once_with(gid=3)


class TestToggleWords:
    def test_toggle_enable_all(self, svc, mock_words_helper):
        svc.toggle_words([], "enable")
        mock_words_helper.check_custom_word.assert_called_once_with(enabled=1)

    def test_toggle_disable_by_ids(self, svc, mock_words_helper):
        svc.toggle_words(["g_1", "g_2"], "disable")
        assert mock_words_helper.check_custom_word.call_count == 2

    def test_toggle_invalid_flag(self, svc):
        ok = svc.toggle_words([], "invalid")
        assert ok is False


class TestGetWordById:
    def test_found(self, svc, mock_words_helper):
        mock_words_helper.get_custom_words.return_value = [
            FakeWordRow(ID=1, REPLACED="a", REPLACE="b", FRONT="", BACK="",
                        OFFSET="", TYPE=2, GROUP_ID=1, SEASON=-2, ENABLED=1,
                        REGEX=0, HELP="help")
        ]
        word = svc.get_word_by_id(1)
        assert isinstance(word, WordDTO)
        assert word.replaced == "a"

    def test_not_found(self, svc, mock_words_helper):
        mock_words_helper.get_custom_words.return_value = []
        assert svc.get_word_by_id(1) is None


class TestAnalyseImportCode:
    def test_analyse(self, svc):
        data = {
            "1": {
                "id": 1, "title": "Test", "year": "2020",
                "type": 1, "tmdbid": 123, "season_count": 2,
                "words": {"10": {"id": 10}}
            }
        }
        raw = json.dumps(data) + "@@@@@@note"
        code = base64.b64encode(raw.encode("utf-8")).decode('utf-8')
        groups, note = svc.analyse_import_code(code)
        assert len(groups) == 1
        assert groups[0].name == "Test（2020）"
        assert groups[0].link == "https://www.themoviedb.org/movie/123"
        assert note == "note"

    def test_analyse_no_tmdbid(self, svc):
        data = {
            "1": {
                "id": 1, "title": "Test", "year": "",
                "type": 2, "tmdbid": None, "season_count": 0,
                "words": {}
            }
        }
        raw = json.dumps(data) + "@@@@@@"
        code = base64.b64encode(raw.encode("utf-8")).decode('utf-8')
        groups, note = svc.analyse_import_code(code)
        assert groups[0].link == ""


class TestExportWords:
    def test_export_all(self, svc, mock_words_helper):
        mock_words_helper.get_custom_word_groups.return_value = [
            FakeWordRow(ID=1, TITLE="G1", YEAR="2020", TYPE=1,
                        TMDBID=100, SEASON_COUNT=1)
        ]
        mock_words_helper.get_custom_words.return_value = [
            FakeWordRow(ID=10, REPLACED="a", REPLACE="b", FRONT="", BACK="",
                        OFFSET="", TYPE=1, GROUP_ID=1, SEASON=-2, ENABLED=1,
                        REGEX=0, HELP="")
        ]
        encoded, note = svc.export_words()
        decoded = base64.b64decode(encoded.encode("utf-8")).decode('utf-8')
        assert "@@@@@@" in decoded

    def test_export_with_ids(self, svc, mock_words_helper):
        mock_words_helper.get_custom_word_groups.return_value = [
            FakeWordRow(ID=1, TITLE="G1", YEAR="2020", TYPE=1,
                        TMDBID=100, SEASON_COUNT=1)
        ]
        mock_words_helper.get_custom_words.return_value = [
            FakeWordRow(ID=10, REPLACED="a", REPLACE="b", FRONT="", BACK="",
                        OFFSET="", TYPE=1, GROUP_ID=1, SEASON=-2, ENABLED=1,
                        REGEX=0, HELP="")
        ]
        encoded, _ = svc.export_words(ids_info="1_10", note="test")
        decoded = base64.b64decode(encoded.encode("utf-8")).decode('utf-8')
        assert "test" in decoded


class TestImportWords:
    def test_import_success(self, svc, mock_words_helper):
        mock_words_helper.is_custom_word_group_existed.return_value = False
        mock_words_helper.is_custom_words_existed.return_value = False
        mock_words_helper.get_custom_word_groups.return_value = [
            FakeWordRow(ID=99, TITLE="New", YEAR="2020", TYPE=1,
                        TMDBID=100, SEASON_COUNT=0)
        ]
        data = {
            "1": {
                "id": 1, "title": "Test", "year": "2020",
                "type": 1, "tmdbid": 100, "season_count": 0,
                "words": {
                    "10": {
                        "id": 10, "replaced": "a", "replace": "b",
                        "front": "", "back": "", "offset": "",
                        "type": 1, "season": -2, "regex": 0, "help": ""
                    }
                }
            }
        }
        raw = json.dumps(data) + "@@@@@@note"
        code = base64.b64encode(raw.encode("utf-8")).decode('utf-8')
        ok, msg = svc.import_words(code, ids_info="1_10")
        assert ok is True
        mock_words_helper.insert_custom_word.assert_called_once()

    def test_import_word_exists(self, svc, mock_words_helper):
        mock_words_helper.is_custom_words_existed.return_value = True
        data = {
            "1": {
                "id": 1, "title": "Test", "year": "2020",
                "type": 1, "tmdbid": 100, "season_count": 0,
                "words": {
                    "10": {
                        "id": 10, "replaced": "a", "replace": "b",
                        "front": "", "back": "", "offset": "",
                        "type": 1, "season": -2, "regex": 0, "help": ""
                    }
                }
            }
        }
        raw = json.dumps(data) + "@@@@@@note"
        code = base64.b64encode(raw.encode("utf-8")).decode('utf-8')
        ok, msg = svc.import_words(code, ids_info="1_10")
        assert ok is False
        assert "已存在" in msg


class TestGetAllWordGroups:
    def test_get_groups(self, svc, mock_words_helper):
        mock_words_helper.get_custom_words.side_effect = lambda **kwargs: [
            FakeWordRow(ID=1, REPLACED="a", REPLACE="b", FRONT="", BACK="",
                        OFFSET="", TYPE=1, GROUP_ID=-1, SEASON=-2, ENABLED=1,
                        REGEX=0, HELP="")
        ] if kwargs.get("gid") == -1 else [
            FakeWordRow(ID=2, REPLACED="c", REPLACE="d", FRONT="", BACK="",
                        OFFSET="", TYPE=2, GROUP_ID=1, SEASON=1, ENABLED=1,
                        REGEX=0, HELP="")
        ]
        mock_words_helper.get_custom_word_groups.return_value = [
            FakeWordRow(ID=1, TITLE="G1", YEAR="2020", TYPE=1,
                        TMDBID=100, SEASON_COUNT=1)
        ]
        groups = svc.get_all_word_groups()
        assert len(groups) == 2
        assert groups[0]["name"] == "通用"
        assert groups[1]["name"] == "G1 (2020)"
