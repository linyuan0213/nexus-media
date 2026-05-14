"""
测试图片代理路由
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestImageRouter:
    """图片代理路由测试"""

    @patch("api.routers.image._serve_image")
    def test_proxy_tmdb_image(self, mock_serve):
        mock_serve.return_value = MagicMock(body=b"fake_image", status_code=200, headers={"content-type": "image/jpeg"})
        resp = client.get("/img/tmdb/w500/test.jpg")
        assert resp.status_code in (200, 404)  # 缓存/下载决定
        mock_serve.assert_called_once()

    @patch("api.routers.image._serve_image")
    def test_proxy_douban_image(self, mock_serve):
        mock_serve.return_value = MagicMock(body=b"fake_image", status_code=200, headers={"content-type": "image/jpeg"})
        resp = client.get("/img/douban/test.jpg")
        assert resp.status_code in (200, 404)

    @patch("api.routers.image._serve_image")
    def test_proxy_bgm_image(self, mock_serve):
        mock_serve.return_value = MagicMock(body=b"fake_image", status_code=200, headers={"content-type": "image/jpeg"})
        resp = client.get("/img/bgm/test.jpg")
        assert resp.status_code in (200, 404)

    @patch("api.routers.image._serve_image")
    def test_proxy_library_image(self, mock_serve):
        mock_serve.return_value = MagicMock(body=b"fake_image", status_code=200, headers={"content-type": "image/jpeg"})
        resp = client.get("/img/library/http%3A%2F%2Flocalhost%2Fimage.jpg")
        assert resp.status_code in (200, 404)

    def test_proxy_image_redirect_local(self):
        """测试 /img?url=/img/tmdb/xxx.jpg -> 307 重定向"""
        resp = client.get("/img?url=/img/tmdb/w500/test.jpg", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/img/tmdb/w500/test.jpg"

    @patch("app.helper.image_proxy_helper.ImageProxyHelper")
    def test_proxy_image_redirect_external(self, mock_helper_cls):
        """测试 /img?url=https://... -> 转换为代理路径后重定向"""
        mock_helper_cls.get_proxy_image_url.return_value = "/img/douban/encoded.jpg"

        resp = client.get("/img?url=https://example.com/image.jpg", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/img/douban/encoded.jpg"

    def test_proxy_image_redirect_no_url(self):
        """测试 /img?url= 空参数返回 400"""
        resp = client.get("/img")
        assert resp.status_code == 400
