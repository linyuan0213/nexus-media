"""
测试 WebUtils.search_media_infos 的 source 参数处理
- source="tmdb" 只搜 TMDB
- source="douban" 只搜豆瓣
- source="" 或 None 同时搜索并去重
"""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.types import MediaType


class FakeMetaInfo:
    """用于替换 MetaInfo 的轻量 mock"""

    def __init__(self, title, year=None, mtype=MediaType.MOVIE, tmdb_id="1"):
        self.title = title
        self.year = year
        self.type = mtype
        self.begin_season = None
        self.begin_episode = None
        self.tmdb_id = tmdb_id
        self.douban_id = None
        self.overview = ""
        self.vote_average = ""
        self.imdb_id = ""
        self.poster_path = ""
        self.cn_name = title
        self.en_name = ""

    def get_name(self):
        return self.title

    def set_tmdb_info(self, info):
        self.title = info.get("title") or self.title
        self.type = MediaType.MOVIE if info.get("media_type") == "movie" else MediaType.TV
        self.tmdb_id = info.get("id") or self.tmdb_id

    def to_dict(self):
        return {
            "id": self.tmdb_id,
            "title": self.title,
            "year": self.year,
            "type": self.type.value if self.type else "",
        }

    def get_backdrop_image(self):
        return ""

    def get_poster_image(self):
        return self.poster_path


@pytest.fixture
def mock_deps():
    with (
        patch("app.utils.web_utils.StringUtils.get_keyword_from_string") as mock_kw,
        patch("app.utils.web_utils.MetaInfo") as mock_meta,
        patch("app.utils.web_utils.Media") as mock_media_cls,
        patch("app.utils.web_utils.DouBan") as mock_douban_cls,
    ):
        # 模拟 keyword 解析结果: (mtype, key_word, season, episode, _, content)
        mock_kw.return_value = (None, "千与千寻", None, None, None, "千与千寻")

        # 每次构造 MetaInfo 都返回 FakeMetaInfo
        mock_meta.side_effect = lambda title: FakeMetaInfo(title=title)

        # Mock TMDB 媒体库
        mock_media = MagicMock()
        mock_media.get_tmdb_infos.return_value = [
            {"id": 1, "title": "千与千寻", "media_type": "movie"},
        ]
        mock_media_cls.return_value = mock_media

        # Mock 豆瓣
        mock_douban = MagicMock()
        mock_douban.search_douban_medias.return_value = [
            FakeMetaInfo(title="千与千寻", year="2001", mtype=MediaType.MOVIE, tmdb_id="DB:1291561"),
        ]
        mock_douban_cls.return_value = mock_douban

        yield {
            "kw": mock_kw,
            "meta": mock_meta,
            "media": mock_media,
            "douban": mock_douban,
        }


class TestSearchMediaInfos:
    def test_source_tmdb_only(self, mock_deps):
        from app.utils.web_utils import WebUtils

        results = WebUtils.search_media_infos("千与千寻", source="tmdb")
        assert len(results) == 1
        assert results[0].title == "千与千寻"
        mock_deps["douban"].search_douban_medias.assert_not_called()

    def test_source_douban_only(self, mock_deps):
        from app.utils.web_utils import WebUtils

        results = WebUtils.search_media_infos("千与千寻", source="douban")
        assert len(results) == 1
        assert results[0].title == "千与千寻"
        mock_deps["media"].get_tmdb_infos.assert_not_called()

    def test_source_empty_merge_and_dedup(self, mock_deps):
        """空 source 时同时搜索并去重相同结果"""
        from app.utils.web_utils import WebUtils

        mock_deps["media"].get_tmdb_infos.return_value = [
            {"id": 1, "title": "千与千寻", "media_type": "movie"},
        ]
        mock_deps["douban"].search_douban_medias.return_value = [
            FakeMetaInfo(title="千与千寻", year="", mtype=MediaType.MOVIE, tmdb_id="DB:1291561"),
        ]
        results = WebUtils.search_media_infos("千与千寻", source="")
        assert len(results) == 1
        mock_deps["media"].get_tmdb_infos.assert_called_once()
        mock_deps["douban"].search_douban_medias.assert_called_once()

    def test_source_none_merge_and_dedup(self, mock_deps):
        from app.utils.web_utils import WebUtils

        mock_deps["media"].get_tmdb_infos.return_value = [
            {"id": 1, "title": "千与千寻", "media_type": "movie"},
        ]
        mock_deps["douban"].search_douban_medias.return_value = [
            FakeMetaInfo(title="千与千寻", year="", mtype=MediaType.MOVIE, tmdb_id="DB:1291561"),
        ]
        results = WebUtils.search_media_infos("千与千寻", source=None)
        assert len(results) == 1

    def test_source_empty_different_results(self, mock_deps):
        """空 source 时不同结果保留"""
        from app.utils.web_utils import WebUtils

        mock_deps["media"].get_tmdb_infos.return_value = [
            {"id": 1, "title": "千与千寻", "media_type": "movie"},
            {"id": 2, "title": "千与千寻2", "media_type": "movie"},
        ]
        mock_deps["douban"].search_douban_medias.return_value = [
            FakeMetaInfo(title="千与千寻", year="", mtype=MediaType.MOVIE, tmdb_id="DB:1291561"),
            FakeMetaInfo(title="千与千寻：豆瓣特供", year="", mtype=MediaType.MOVIE, tmdb_id="DB:999"),
        ]
        results = WebUtils.search_media_infos("千与千寻", source="")
        titles = [r.title for r in results]
        assert "千与千寻" in titles
        assert "千与千寻2" in titles
        assert "千与千寻：豆瓣特供" in titles
        assert len(results) == 3
