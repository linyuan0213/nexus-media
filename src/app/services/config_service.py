"""
ConfigService - 配置业务服务层

封装对全局单例 config.Config 的访问，使路由层不再直接引用 Config 单例。
支持构造函数注入，便于单元测试时替换为 mock。
"""

from typing import Any

from app.core.exceptions import DomainError, RepositoryError, ServiceError  # noqa: F401
from app.core.settings import settings
from app.utils.config_tools import get_domain, get_proxies, get_tmdbapi_url, get_ua
from app.utils.path_utils import get_category_path, get_script_path, get_temp_path, get_user_plugin_path


class ConfigService:
    """
    配置服务：统一收口对 config.yaml 的读取与变更。

    设计原则：
    - 路由层通过 `Depends(get_config_service)` 注入，不直接 `from config import Config`。
    - 测试时可直接传入 mock 实例，无需 monkey-patch 全局单例。
    """

    def __init__(self, config: Any | None = None):
        self._config = config or settings

    # ------------------------------------------------------------------
    # 读取接口
    # ------------------------------------------------------------------

    def get_config(self, node: str | None = None) -> Any:
        """获取完整配置或指定节点配置"""
        return self._config.get(node)

    def get_pt_config(self) -> dict:
        """获取 PT 配置节点"""
        return self._config.get("pt") or {}

    def get_media_config(self) -> dict:
        """获取媒体配置节点"""
        return self._config.get("media") or {}

    def get_app_config(self) -> dict:
        """获取应用配置节点"""
        return self._config.get("app") or {}

    def get_script_path(self) -> str:
        """获取 SQL 脚本路径"""

        return get_script_path()

    def get_proxies(self) -> dict | None:
        """获取代理配置"""

        return get_proxies()

    def get_ua(self) -> str:
        """获取 User-Agent"""

        return get_ua()

    def get_domain(self) -> str | None:
        """获取站点域名"""

        return get_domain()

    def get_config_path(self) -> str:
        """获取配置目录路径"""
        return self._config.config_path

    def get_temp_path(self) -> str:
        """获取临时目录路径"""

        return get_temp_path()

    def get_user_plugin_path(self) -> str:
        """获取用户插件目录路径"""

        return get_user_plugin_path()

    def get_tmdbapi_url(self) -> str:
        """获取 TMDB API URL"""

        return get_tmdbapi_url()

    @property
    def category_path(self) -> str | None:
        """获取分类配置文件路径"""

        return get_category_path()

    # ------------------------------------------------------------------
    # 写入接口
    # ------------------------------------------------------------------

    def save_config(self, new_cfg: dict) -> None:
        """保存完整配置"""
        self._config.save(new_cfg)

    def update_node(self, node: str, value: dict) -> None:
        """更新指定节点配置并保存"""
        cfg = self._config.get()
        cfg[node] = value
        self._config.save(cfg)

    # ------------------------------------------------------------------
    # 兼容属性
    # ------------------------------------------------------------------

    def reload(self) -> bool | None:
        """重新加载配置（谨慎使用）"""
        self._config.reload()
        return True
