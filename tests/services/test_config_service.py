"""
ConfigService 测试
"""

from unittest.mock import MagicMock

import pytest

# 直接从子模块导入，避免触发 app.services.__init__ 中的重型初始化
from app.services.config_service import ConfigService


class TestConfigService:
    """测试配置服务"""

    @pytest.fixture
    def mock_config(self):
        """创建一个 mock Config 对象"""
        config = MagicMock()
        _cfg_data = {
            "app": {"proxies": {"http": "http://127.0.0.1:7890"}},
            "pt": {"pt_check_interval": 300},
            "media": {"media_default_path": "/media"},
        }

        def _get_config(node=None):
            if node is None:
                return _cfg_data
            return _cfg_data.get(node, {})

        config.get_config.side_effect = _get_config
        config.get_script_path.return_value = "/scripts/sqls"
        config.get_proxies.return_value = {"http": "http://127.0.0.1:7890"}
        config.get_ua.return_value = "Mozilla/5.0 Test"
        config.get_domain.return_value = "http://localhost"
        config.get_config_path.return_value = "/config"
        config.get_temp_path.return_value = "/config/temp"
        config.get_user_plugin_path.return_value = "/config/plugins"
        config.get_tmdbapi_url.return_value = "https://api.themoviedb.org/3"
        config.category_path = "/config/category.yaml"
        config.current_user = "admin"
        return config

    def test_get_config_all(self, mock_config):
        """获取完整配置"""
        svc = ConfigService(config=mock_config)
        result = svc.get_config()
        assert result == {
            "app": {"proxies": {"http": "http://127.0.0.1:7890"}},
            "pt": {"pt_check_interval": 300},
            "media": {"media_default_path": "/media"},
        }
        mock_config.get_config.assert_called_once_with(None)

    def test_get_config_node(self, mock_config):
        """获取指定节点配置"""
        svc = ConfigService(config=mock_config)
        result = svc.get_config("app")
        mock_config.get_config.assert_called_with("app")

    def test_get_pt_config(self, mock_config):
        """获取 PT 配置"""
        svc = ConfigService(config=mock_config)
        result = svc.get_pt_config()
        assert result == {"pt_check_interval": 300}

    def test_get_media_config(self, mock_config):
        """获取媒体配置"""
        svc = ConfigService(config=mock_config)
        result = svc.get_media_config()
        assert result == {"media_default_path": "/media"}

    def test_get_app_config(self, mock_config):
        """获取应用配置"""
        svc = ConfigService(config=mock_config)
        result = svc.get_app_config()
        assert result == {"proxies": {"http": "http://127.0.0.1:7890"}}

    def test_get_script_path(self, mock_config):
        """获取脚本路径"""
        svc = ConfigService(config=mock_config)
        result = svc.get_script_path()
        assert result == "/scripts/sqls"

    def test_get_proxies(self, mock_config):
        """获取代理配置"""
        svc = ConfigService(config=mock_config)
        result = svc.get_proxies()
        assert result == {"http": "http://127.0.0.1:7890"}

    def test_get_ua(self, mock_config):
        """获取 User-Agent"""
        svc = ConfigService(config=mock_config)
        result = svc.get_ua()
        assert result == "Mozilla/5.0 Test"

    def test_get_domain(self, mock_config):
        """获取站点域名"""
        svc = ConfigService(config=mock_config)
        result = svc.get_domain()
        assert result == "http://localhost"

    def test_get_config_path(self, mock_config):
        """获取配置目录路径"""
        svc = ConfigService(config=mock_config)
        result = svc.get_config_path()
        assert result == "/config"

    def test_get_temp_path(self, mock_config):
        """获取临时目录路径"""
        svc = ConfigService(config=mock_config)
        result = svc.get_temp_path()
        assert result == "/config/temp"

    def test_get_user_plugin_path(self, mock_config):
        """获取用户插件目录路径"""
        svc = ConfigService(config=mock_config)
        result = svc.get_user_plugin_path()
        assert result == "/config/plugins"

    def test_get_tmdbapi_url(self, mock_config):
        """获取 TMDB API URL"""
        svc = ConfigService(config=mock_config)
        result = svc.get_tmdbapi_url()
        assert result == "https://api.themoviedb.org/3"

    def test_category_path_property(self, mock_config):
        """获取分类路径属性"""
        svc = ConfigService(config=mock_config)
        result = svc.category_path
        assert result == "/config/category.yaml"

    def test_current_user_property(self, mock_config):
        """获取和设置当前用户"""
        svc = ConfigService(config=mock_config)
        assert svc.current_user == "admin"
        svc.current_user = "testuser"
        assert mock_config.current_user == "testuser"

    def test_save_config(self, mock_config):
        """保存配置"""
        svc = ConfigService(config=mock_config)
        new_cfg = {"app": {"new_key": "new_value"}}
        svc.save_config(new_cfg)
        mock_config.save_config.assert_called_once_with(new_cfg)

    def test_update_node(self, mock_config):
        """更新指定节点"""
        svc = ConfigService(config=mock_config)
        svc.update_node("pt", {"new": "value"})
        mock_config.save_config.assert_called_once()
        call_args = mock_config.save_config.call_args[0][0]
        assert call_args["pt"] == {"new": "value"}

    def test_default_config_instance(self):
        """默认使用全局 Config 单例"""
        with pytest.MonkeyPatch().context() as m:
            mock_cfg_cls = MagicMock()
            mock_cfg_cls.return_value = MagicMock()
            m.setattr("app.services.config_service.Config", mock_cfg_cls)
            svc = ConfigService()
            mock_cfg_cls.assert_called_once()
