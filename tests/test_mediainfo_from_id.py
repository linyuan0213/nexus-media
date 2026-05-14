"""
测试 get_mediainfo_from_id 函数
验证豆瓣和Bangumi媒体在无法匹配TMDB时的处理
"""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.types import MediaType
from web.backend.web_utils import WebUtils


class TestGetMediainfoFromId:
    """测试 get_mediainfo_from_id 函数"""

    def test_douban_media_no_tmdb_match(self):
        """
        测试豆瓣媒体无法匹配到TMDB时返回None
        """
        with patch("web.backend.web_utils.DouBan") as mock_douban, patch("web.backend.web_utils.Media") as mock_media:
            # 模拟豆瓣返回信息
            mock_douban_instance = MagicMock()
            mock_douban_instance.get_douban_detail.return_value = {
                "title": "测试电影",
                "original_title": "Test Movie",
                "year": "2023",
                "cover_url": "http://example.com/cover.jpg",
            }
            mock_douban.return_value = mock_douban_instance

            # 模拟Media().get_media_info返回没有tmdb_info的对象
            mock_media_info = MagicMock()
            mock_media_info.tmdb_info = None  # 没有TMDB信息

            mock_media_instance = MagicMock()
            mock_media_instance.get_media_info.return_value = mock_media_info
            mock_media.return_value = mock_media_instance

            # 调用函数
            result = WebUtils.get_mediainfo_from_id(mtype=MediaType.MOVIE, mediaid="DB:12345")

            # 验证返回None，因为无法匹配到TMDB
            assert result is None, "豆瓣媒体无法匹配TMDB时应返回None"

    def test_bangumi_media_no_tmdb_match(self):
        """
        测试Bangumi媒体无法匹配到TMDB时返回None
        """
        with patch("web.backend.web_utils.Bangumi") as mock_bangumi, patch("web.backend.web_utils.Media") as mock_media:
            # 模拟Bangumi返回信息
            mock_bangumi_obj = MagicMock()
            mock_bangumi_obj.detail.return_value = {"name": "Test Anime", "name_cn": "测试动漫", "date": "2023-01-01"}
            mock_bangumi.return_value = mock_bangumi_obj

            # 模拟Media().get_media_info返回没有tmdb_info的对象
            mock_media_info = MagicMock()
            mock_media_info.tmdb_info = None  # 没有TMDB信息

            mock_media_obj = MagicMock()
            mock_media_obj.get_media_info.return_value = mock_media_info
            mock_media.return_value = mock_media_obj

            # 调用函数
            result = WebUtils.get_mediainfo_from_id(mtype=MediaType.TV, mediaid="BG:12345")

            # 验证返回None，因为无法匹配到TMDB
            assert result is None, "Bangumi媒体无法匹配TMDB时应返回None"

    def test_douban_media_with_tmdb_match(self):
        """
        测试豆瓣媒体成功匹配到TMDB时返回正确对象
        """
        with patch("web.backend.web_utils.DouBan") as mock_douban, patch("web.backend.web_utils.Media") as mock_media:
            # 模拟豆瓣返回信息
            mock_douban_obj = MagicMock()
            mock_douban_obj.get_douban_detail.return_value = {
                "title": "肖申克的救赎",
                "original_title": "The Shawshank Redemption",
                "year": "1994",
                "cover_url": "http://example.com/cover.jpg",
            }
            mock_douban.return_value = mock_douban_obj

            # 模拟Media().get_media_info返回有tmdb_info的对象
            mock_media_info = MagicMock()
            mock_media_info.tmdb_info = {"id": 278, "title": "The Shawshank Redemption"}
            mock_media_info.poster_path = "/poster.jpg"

            mock_media_obj = MagicMock()
            mock_media_obj.get_media_info.return_value = mock_media_info
            mock_media.return_value = mock_media_obj

            # 调用函数
            result = WebUtils.get_mediainfo_from_id(mtype=MediaType.MOVIE, mediaid="DB:12345")

            # 验证返回正确的媒体信息对象
            assert result is not None, "豆瓣媒体匹配到TMDB时应返回媒体信息"
            assert result.tmdb_info is not None, "返回的对象应有tmdb_info"
            assert result.douban_id == "12345", "应设置正确的豆瓣ID"

    def test_bangumi_media_with_tmdb_match(self):
        """
        测试Bangumi媒体成功匹配到TMDB时返回正确对象
        """
        with patch("web.backend.web_utils.Bangumi") as mock_bangumi, patch("web.backend.web_utils.Media") as mock_media:
            # 模拟Bangumi返回信息
            mock_bangumi_obj = MagicMock()
            mock_bangumi_obj.detail.return_value = {
                "name": "Attack on Titan",
                "name_cn": "进击的巨人",
                "date": "2013-04-06",
            }
            mock_bangumi.return_value = mock_bangumi_obj

            # 模拟Media().get_media_info返回有tmdb_info的对象
            mock_media_info = MagicMock()
            mock_media_info.tmdb_info = {"id": 1429, "name": "Attack on Titan"}

            mock_media_obj = MagicMock()
            mock_media_obj.get_media_info.return_value = mock_media_info
            mock_media.return_value = mock_media_obj

            # 调用函数
            result = WebUtils.get_mediainfo_from_id(mtype=MediaType.TV, mediaid="BG:12345")

            # 验证返回正确的媒体信息对象
            assert result is not None, "Bangumi媒体匹配到TMDB时应返回媒体信息"
            assert result.tmdb_info is not None, "返回的对象应有tmdb_info"

    def test_tmdb_media_direct(self):
        """
        测试直接通过TMDB ID获取媒体信息
        """
        with patch("web.backend.web_utils.Media") as mock_media:
            # 模拟get_tmdb_info返回信息
            mock_media_obj = MagicMock()
            mock_media_obj.get_tmdb_info.return_value = {
                "id": 278,
                "title": "The Shawshank Redemption",
                "media_type": MediaType.MOVIE,
            }
            mock_media.return_value = mock_media_obj

            # 调用函数
            result = WebUtils.get_mediainfo_from_id(mtype=MediaType.MOVIE, mediaid="278")

            # 验证返回正确的媒体信息对象
            assert result is not None, "TMDB ID应直接返回媒体信息"

    def test_empty_mediaid(self):
        """
        测试空mediaid返回None
        """
        result = WebUtils.get_mediainfo_from_id(mtype=MediaType.MOVIE, mediaid="")
        assert result is None, "空mediaid应返回None"

        result = WebUtils.get_mediainfo_from_id(mtype=MediaType.MOVIE, mediaid=None)
        assert result is None, "None mediaid应返回None"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
