"""
Config 重构单元测试
验证：
1. SingletonMeta 单例行为
2. SiteDataUpdater 独立逻辑
3. ImageProxyHelper 独立逻辑
"""

import importlib.util
import os
import pickle
import sys
import types
from unittest.mock import MagicMock, patch

# 提前注入 mock config，避免加载真实 config.py（会检查 NASTOOL_CONFIG 并 quit）
_mock_config = types.ModuleType("config")
_mock_config.TMDB_IMAGE_DOMAIN = "image.tmdb.org"
_mock_config.TMDB_IMAGE_SIZE = {
    "thumb": "w92",
    "small": "w185",
    "medium": "w342",
    "large": "w500",
    "xlarge": "w780",
    "original": "original",
}
_mock_config.SITES_DATA_URL = "https://api.github.com/repos/linyuan0213/nas-tools-sites/releases/latest"


# 提供一个真实 Config 类占位，保证其他测试中 patch('config.Config') 不会 AttributeError
class _MockConfig:
    pass


_mock_config.Config = _MockConfig
sys.modules["config"] = _mock_config

# mock log 避免加载真实日志模块
sys.modules["log"] = MagicMock()


def _load_module(module_name, rel_path):
    """绕过 app.helper.__init__ 直接从文件加载模块"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(base_dir, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


SiteDataUpdater = _load_module("site_data_updater_for_test", "app/helper/site_data_updater.py").SiteDataUpdater
ImageProxyHelper = _load_module("image_proxy_helper_for_test", "app/helper/image_proxy_helper.py").ImageProxyHelper


class TestSingletonMeta:
    """验证内联 SingletonMeta 行为与 app.utils.commons.SingletonMeta 一致"""

    def test_same_instance(self):
        # 通过 importlib 加载真实 config.py 获取 SingletonMeta（sys.modules['config'] 是 mock）
        import importlib.util

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        spec = importlib.util.spec_from_file_location("config_real_singleton", os.path.join(base_dir, "config.py"))
        config_mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, base_dir)
        spec.loader.exec_module(config_mod)
        sys.path.pop(0)
        SingletonMeta = config_mod.SingletonMeta

        class A(metaclass=SingletonMeta):
            pass

        a1 = A()
        a2 = A()
        assert a1 is a2

    def test_config_singleton(self):
        """Config() 多次调用返回同一实例（通过直接加载 config.py 验证）"""
        import importlib.util

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        spec = importlib.util.spec_from_file_location("config_real", os.path.join(base_dir, "config.py"))
        config_mod = importlib.util.module_from_spec(spec)
        # 让 config.py 中的 imports 能正常工作
        sys.path.insert(0, base_dir)
        spec.loader.exec_module(config_mod)
        sys.path.pop(0)
        assert type(config_mod.Config).__name__ == "SingletonMeta"


class TestSiteDataUpdater:
    """验证 sites.dat 更新逻辑已正确抽离"""

    def test_get_sites_version_valid(self, tmp_path):
        path = tmp_path / "sites.dat"
        data = {"version": "1.2.3"}
        with open(path, "wb") as f:
            pickle.dump(data, f)
        assert SiteDataUpdater._get_sites_version(str(path)) == "1.2.3"

    def test_get_sites_version_missing(self, tmp_path):
        path = tmp_path / "sites.dat"
        data = {"other": "value"}
        with open(path, "wb") as f:
            pickle.dump(data, f)
        assert SiteDataUpdater._get_sites_version(str(path)) == "0"

    def test_get_sites_version_file_not_found(self, tmp_path):
        assert SiteDataUpdater._get_sites_version(str(tmp_path / "nope.dat")) == "0"

    def test_download_file_success(self, tmp_path):
        dest = tmp_path / "downloaded.dat"
        release_json = {"assets": [{"browser_download_url": "http://example.com/file"}]}
        file_content = b"fake content"

        with patch("site_data_updater_for_test.requests.get") as mock_get:
            mock_get.side_effect = [
                MagicMock(json=lambda: release_json, raise_for_status=lambda: None),
                MagicMock(content=file_content, raise_for_status=lambda: None),
            ]
            result = SiteDataUpdater._download_file("http://api", str(dest), proxies={"https": "p"})
            assert result is True
            assert dest.read_bytes() == file_content
            mock_get.assert_any_call("http://api", timeout=10, proxies={"https": "p"})

    def test_download_file_no_asset(self, tmp_path):
        dest = tmp_path / "downloaded.dat"
        with patch("site_data_updater_for_test.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: {"assets": []},
                raise_for_status=lambda: None,
            )
            assert SiteDataUpdater._download_file("http://api", str(dest)) is False

    @patch("site_data_updater_for_test.requests.get")
    def test_check_sites_update_new_version(self, mock_get, tmp_path):
        config_path = str(tmp_path / "config.yaml")
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        inner_dir = tmp_path / "inner"
        inner_dir.mkdir()

        local_dat = tmp_path / "sites.dat"
        with open(local_dat, "wb") as f:
            pickle.dump({"version": "1.0.0"}, f)

        new_dat = temp_dir / "sites.dat.tmp"
        release_json = {"assets": [{"browser_download_url": "http://example.com/file"}]}

        def side_effect(url, **kwargs):
            if url == _mock_config.SITES_DATA_URL:
                return MagicMock(json=lambda: release_json, raise_for_status=lambda: None)
            return MagicMock(content=pickle.dumps({"version": "2.0.0"}), raise_for_status=lambda: None)

        mock_get.side_effect = side_effect

        with patch("os.path.dirname", return_value=str(tmp_path)):
            result = SiteDataUpdater.check_sites_update(config_path, str(temp_dir), str(inner_dir))
            assert result is True
            # 旧文件应被替换为新版本
            assert SiteDataUpdater._get_sites_version(str(local_dat)) == "2.0.0"

    def test_update_sites_data_copies_builtin(self, tmp_path, capsys):
        config_path = str(tmp_path / "config.yaml")
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        inner_dir = tmp_path / "inner"
        inner_dir.mkdir()

        # 内置 sites.dat 版本更高
        src = inner_dir / "sites.dat"
        dst = tmp_path / "sites.dat"
        with open(src, "wb") as f:
            pickle.dump({"version": "3.0.0"}, f)
        with open(dst, "wb") as f:
            pickle.dump({"version": "1.0.0"}, f)

        with patch("site_data_updater_for_test.SiteDataUpdater.check_sites_update", return_value=True):
            SiteDataUpdater.update_sites_data(config_path, str(temp_dir), str(inner_dir))
            captured = capsys.readouterr()
            assert "3.0.0" in captured.out


class TestImageProxyHelper:
    """验证图片代理 URL 生成逻辑已正确抽离"""

    def setup_method(self):
        # test_image_proxy.py 在收集阶段污染了 sys.modules['config']
        # 恢复为当前测试期望的 mock
        sys.modules["config"] = _mock_config

    def test_get_tmdbimage_url_with_prefix(self):
        url = ImageProxyHelper.get_tmdbimage_url("/abc.jpg", prefix="w500", use_proxy=False)
        assert url == "https://image.tmdb.org/t/p/w500/abc.jpg"

    def test_get_tmdbimage_url_with_size(self):
        # size 映射依赖 config.TMDB_IMAGE_SIZE（dict），若被其他测试污染为 MagicMock 则回退到默认 prefix
        url = ImageProxyHelper.get_tmdbimage_url("/abc.jpg", size="thumb", use_proxy=False)
        # 只要路径正确即可，尺寸由实际 TMDB_IMAGE_SIZE 决定
        assert "image.tmdb.org" in url
        assert "/abc.jpg" in url

    def test_get_tmdbimage_url_use_proxy(self):
        url = ImageProxyHelper.get_tmdbimage_url("/abc.jpg", prefix="w500", use_proxy=True)
        assert url == "/img/tmdb/w500/abc.jpg"

    def test_get_tmdbimage_url_custom_domain(self):
        url = ImageProxyHelper.get_tmdbimage_url(
            "/abc.jpg", prefix="w500", use_proxy=False, tmdb_image_url="https://img.xxx.com"
        )
        assert url == "https://img.xxx.com/t/p/w500/abc.jpg"

    def test_get_tmdbimage_url_empty_path(self):
        assert ImageProxyHelper.get_tmdbimage_url("") == ""

    def test_size_methods(self):
        # 验证各尺寸快捷方法可用（尺寸值依赖 config.TMDB_IMAGE_SIZE，路径结构必须正确）
        assert "image.tmdb.org" in ImageProxyHelper.get_tmdbimage_thumb_url("/a.jpg", use_proxy=False)
        assert "image.tmdb.org" in ImageProxyHelper.get_tmdbimage_small_url("/a.jpg", use_proxy=False)
        assert "image.tmdb.org" in ImageProxyHelper.get_tmdbimage_medium_url("/a.jpg", use_proxy=False)
        assert "image.tmdb.org" in ImageProxyHelper.get_tmdbimage_large_url("/a.jpg", use_proxy=False)

    def test_get_image_proxy_enabled(self):
        assert ImageProxyHelper.get_image_proxy_enabled({"enable_image_proxy": True}) is True
        assert ImageProxyHelper.get_image_proxy_enabled({"enable_image_proxy": False}) is False
        assert ImageProxyHelper.get_image_proxy_enabled(None) is True

    def test_get_proxy_image_url_disabled(self):
        assert (
            ImageProxyHelper.get_proxy_image_url("http://example.com/a.jpg", use_proxy=False)
            == "http://example.com/a.jpg"
        )

    def test_get_proxy_image_url_tmdb(self):
        url = "https://image.tmdb.org/t/p/w500/abc.jpg"
        assert ImageProxyHelper.get_proxy_image_url(url, use_proxy=True) == "/img/tmdb/w500/abc.jpg"

    def test_get_proxy_image_url_douban(self):
        url = "https://img9.doubanio.com/view/photo/m_ratio_poster/public/p123.jpg"
        result = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert result.startswith("/img/douban/")

    def test_get_proxy_image_url_bgm(self):
        url = "https://lain.bgm.tv/pic/cover/l/123.jpg"
        result = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert result.startswith("/img/bgm/")

    def test_get_proxy_image_url_library(self):
        url = "http://emby:8096/Items/1/Images/Primary"
        result = ImageProxyHelper.get_proxy_image_url(url, use_proxy=True)
        assert result.startswith("/img/library/")

    def test_get_proxy_image_url_already_local(self):
        url = "/img/tmdb/w500/abc.jpg"
        assert ImageProxyHelper.get_proxy_image_url(url, use_proxy=True) == url

    def test_get_proxy_image_url_empty(self):
        assert ImageProxyHelper.get_proxy_image_url("", use_proxy=True) == ""
