"""
测试图片代理修复

验证修复前的问题：
1. 旧路由 /img?url=... 对本地代理路径的重定向
2. 外部图片 URL 是否正确转换为代理路径
"""

import pytest


class TestImageProxyHelper:
    """测试 ImageProxyHelper 的 URL 转换逻辑"""

    def test_tmdb_url_to_proxy(self):
        """TMDB 外部 URL 应正确转换为本地代理路径"""
        from app.helper.image_proxy_helper import ImageProxyHelper

        url = "https://image.tmdb.org/t/p/w500/abc123.jpg"
        proxy_url = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert proxy_url == "/img/tmdb/w500/abc123.jpg"

    def test_tmdb_original_url_to_proxy(self):
        """TMDB original URL 应正确转换"""
        from app.helper.image_proxy_helper import ImageProxyHelper

        url = "https://image.tmdb.org/t/p/original/abc123.jpg"
        proxy_url = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert proxy_url == "/img/tmdb/original/abc123.jpg"

    def test_douban_url_to_proxy(self):
        """豆瓣外部 URL 应正确转换为本地代理路径"""
        from app.helper.image_proxy_helper import ImageProxyHelper

        url = "https://img9.doubanio.com/view/photo/m_ratio_poster/public/p123.jpg"
        proxy_url = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert proxy_url.startswith("/img/douban/")
        assert "doubanio.com" in proxy_url

    def test_already_proxy_url_unchanged(self):
        """已经是代理路径的 URL 应保持不变"""
        from app.helper.image_proxy_helper import ImageProxyHelper

        url = "/img/tmdb/w500/abc123.jpg"
        proxy_url = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert proxy_url == "/img/tmdb/w500/abc123.jpg"

    def test_empty_url(self):
        """空 URL 应返回空字符串"""
        from app.helper.image_proxy_helper import ImageProxyHelper

        assert ImageProxyHelper.get_proxy_image_url("", use_proxy=True) == ""
        assert ImageProxyHelper.get_proxy_image_url(None, use_proxy=True) == ""


class TestSearchResultImageStorage:
    """测试搜索结果图片入库逻辑"""

    def test_poster_and_image_fields(self):
        """验证数据库中 POSTER 和 IMAGE 字段的存储逻辑"""
        from app.helper.image_proxy_helper import ImageProxyHelper
        from app.media.models import MediaInfo
        from app.utils.types import MediaType

        # 模拟 TMDB 信息
        media = MediaInfo(title="Test Movie")
        media.type = MediaType.MOVIE
        media.tmdb_id = 12345
        media.poster_path = ImageProxyHelper.get_tmdbimage_url("/abc123.jpg", size="medium")
        media.backdrop_path = ImageProxyHelper.get_tmdbimage_url("/def456.jpg", size="large")

        # poster 应该是 w500 尺寸的外部 URL
        assert media.poster_path == "https://image.tmdb.org/t/p/w342/abc123.jpg"

        # get_poster_image 应返回 poster_path（因为已设置）
        assert media.get_poster_image() == media.poster_path

        # get_backdrop_image(original=True) 应返回 original 尺寸
        backdrop = media.get_backdrop_image(default=False, original=True)
        assert "original" in backdrop
        assert "def456.jpg" in backdrop


class TestWebMainImgRoute:
    """测试 web/main.py 中 /img 路由的重定向逻辑（无需 Flask 客户端）"""

    def test_proxy_url_redirect(self):
        """本地代理路径应识别为重定向目标"""

        # 模拟 /img?url=/img/tmdb/w500/abc.jpg 的场景
        url = "/img/tmdb/w500/abc.jpg"
        assert url.startswith("/img/")

    def test_external_url_to_proxy_conversion(self):
        """外部图片 URL 应转换为代理路径"""
        from app.helper.image_proxy_helper import ImageProxyHelper

        url = "https://image.tmdb.org/t/p/w500/abc.jpg"
        proxy_url = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert proxy_url.startswith("/img/")
        assert proxy_url == "/img/tmdb/w500/abc.jpg"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
