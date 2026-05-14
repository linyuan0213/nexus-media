"""
图片代理服务测试 - 重点验证媒体库图片本地缓存代理
"""

import importlib.util
import os
import sys
import urllib.parse
from unittest.mock import MagicMock, mock_open, patch

import pytest
from flask import Flask

from web.backend.image_proxy import (
    _get_cache_path,
    img_blueprint,
)

# 提前注入 mock，避免加载真实配置
mock_config = MagicMock()
mock_config.Config.return_value.get_image_proxy_enabled.return_value = True
mock_config.Config.return_value.get_domain.return_value = "http://localhost"
mock_config.Config.return_value.get_proxies.return_value = None
mock_config.TMDB_IMAGE_DOMAIN = "image.tmdb.org"
mock_config.TMDB_IMAGE_SIZE = "w500"

sys.modules["config"] = mock_config

mock_log = MagicMock()
sys.modules["log"] = mock_log

# mock PIL
mock_pil = MagicMock()
sys.modules["PIL"] = mock_pil
sys.modules["PIL.Image"] = mock_pil.Image

# mock web.security 中的 login_required，避免测试需要真实鉴权
mock_security = MagicMock()
mock_security.login_required = lambda f: f
sys.modules["web.security"] = mock_security

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_get_nt_image_url():
    """
    通过 importlib.util 直接从文件加载 _base.py，
    绕过 app.mediaserver 包的 __init__.py，避免触发整个 app 初始化。
    """
    base_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "mediaserver", "client", "_base.py"
    )
    spec = importlib.util.spec_from_file_location("_base_for_test", base_path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._IMediaClient.get_nt_image_url


get_nt_image_url = _load_get_nt_image_url()


@pytest.fixture
def app(tmp_path):
    """创建带图片代理蓝图的测试 Flask 应用"""
    _app = Flask(__name__)
    _app.register_blueprint(img_blueprint, url_prefix="/img")
    _app.config["TESTING"] = True
    return _app


@pytest.fixture
def client(app):
    return app.test_client()


class TestGetNtImageUrl:
    """测试 get_nt_image_url 对媒体库图片的代理路由转换"""

    def test_tmdb_still_uses_tmdb_route(self):
        url = "https://image.tmdb.org/t/p/w500/abc.jpg"
        result = get_nt_image_url(url)
        assert result.startswith("/img/tmdb/")

    def test_douban_still_uses_douban_route(self):
        url = "https://img9.doubanio.com/view/photo/m_ratio_poster/public/p123.jpg"
        result = get_nt_image_url(url)
        assert result.startswith("/img/douban/")

    def test_bgm_still_uses_bgm_route(self):
        url = "https://lain.bgm.tv/pic/cover/l/123.jpg"
        result = get_nt_image_url(url)
        assert result.startswith("/img/bgm/")

    def test_emby_image_uses_library_route(self):
        url = "http://192.168.1.10:8096/Items/123/Images/Primary"
        result = get_nt_image_url(url)
        assert result.startswith("/img/library/")
        decoded = urllib.parse.unquote(result[len("/img/library/") :])
        assert decoded == url

    def test_plex_image_uses_library_route(self):
        url = "http://192.168.1.10:32400/library/metadata/123/thumb"
        result = get_nt_image_url(url)
        assert result.startswith("/img/library/")

    def test_fnos_image_uses_library_route(self):
        url = "http://192.168.1.10/v/api/v1/sys/img/posters/abc.jpg"
        result = get_nt_image_url(url)
        assert result.startswith("/img/library/")

    def test_remote_returns_full_domain(self):
        url = "http://jellyfin:8096/Items/456/Images/Primary"
        result = get_nt_image_url(url, remote=True)
        assert result.startswith("http://localhost/img/library/")


class TestLibraryCachePath:
    """测试媒体库图片缓存路径生成"""

    def test_get_cache_path_contains_library_source(self, tmp_path):
        with patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)):
            path = _get_cache_path("library", "http://host/Items/1/Images/Primary")
            assert "library" in path
            assert path.endswith(".jpg")

    def test_get_cache_path_is_deterministic(self, tmp_path):
        with patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)):
            p1 = _get_cache_path("library", "http://host/img.jpg")
            p2 = _get_cache_path("library", "http://host/img.jpg")
            assert p1 == p2


class TestLibraryImageProxyRoute:
    """测试 /img/library/<path> 路由行为"""

    def test_proxy_library_image_decodes_url_and_saves_cache(self, client, tmp_path):
        with (
            patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)),
            patch("web.backend.image_proxy._download_image") as mock_dl,
            patch("web.backend.image_proxy.os.path.exists", return_value=False),
            patch("builtins.open", mock_open()) as mock_file,
        ):
            mock_dl.return_value = b"fake_image_bytes"
            encoded_url = "http%3A%2F%2Femby%3A8096%2FItems%2F1%2FImages%2FPrimary"
            resp = client.get(f"/img/library/{encoded_url}")

            assert resp.status_code == 200
            assert resp.data == b"fake_image_bytes"
            mock_dl.assert_called_once_with("http://emby:8096/Items/1/Images/Primary", referer=None)
            mock_file.assert_called()

    def test_proxy_library_image_appends_query_params(self, client, tmp_path):
        with (
            patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)),
            patch("web.backend.image_proxy._download_image") as mock_dl,
            patch("web.backend.image_proxy.os.path.exists", return_value=False),
            patch("builtins.open", mock_open()),
        ):
            mock_dl.return_value = b"fake_image_bytes"
            encoded_url = "http%3A%2F%2Fplex%3A32400%2Flibrary%2Fmetadata%2F1%2Fthumb"
            resp = client.get(f"/img/library/{encoded_url}?X-Plex-Token=abc123")

            assert resp.status_code == 200
            mock_dl.assert_called_once_with(
                "http://plex:32400/library/metadata/1/thumb?X-Plex-Token=abc123", referer=None
            )

    def test_proxy_library_image_existing_query_appended_with_ampersand(self, client, tmp_path):
        with (
            patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)),
            patch("web.backend.image_proxy._download_image") as mock_dl,
            patch("web.backend.image_proxy.os.path.exists", return_value=False),
            patch("builtins.open", mock_open()),
        ):
            mock_dl.return_value = b"fake_image_bytes"
            # 原始 URL 里已经带 ?tag=xxx
            encoded_url = "http%3A%2F%2Fplex%3A32400%2Flibrary%2Fmetadata%2F1%2Fthumb%3Ftag%3Dabc"
            resp = client.get(f"/img/library/{encoded_url}?X-Plex-Token=xyz")

            assert resp.status_code == 200
            mock_dl.assert_called_once_with(
                "http://plex:32400/library/metadata/1/thumb?tag=abc&X-Plex-Token=xyz", referer=None
            )

    def test_proxy_library_image_returns_cache_hit(self, client, tmp_path):
        with patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)):
            encoded_url = "http%3A%2F%2Fhost%2Fimg.jpg"
            decoded_url = "http://host/img.jpg"
            cache_path = _get_cache_path("library", decoded_url)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(b"cached_image_bytes")

            resp = client.get(f"/img/library/{encoded_url}")
            assert resp.status_code == 200
            assert resp.data == b"cached_image_bytes"

    def test_proxy_library_image_404_when_download_fails(self, client, tmp_path):
        with (
            patch("web.backend.image_proxy.CACHE_DIR", str(tmp_path)),
            patch("web.backend.image_proxy._download_image", return_value=None),
            patch("web.backend.image_proxy.os.path.exists", return_value=False),
        ):
            encoded_url = "http%3A%2F%2Fhost%2Fmissing.jpg"
            resp = client.get(f"/img/library/{encoded_url}")
            assert resp.status_code == 404
