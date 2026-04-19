# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.conf import SystemConfig
from app.helper import PluginHelper
from app.plugins import PluginManager
from app.utils.types import SystemConfigKey


@dataclass
class PluginAppsDTO:
    plugins: Any = None
    statistic: Any = None


@dataclass
class PluginPageDTO:
    title: Optional[str] = None
    content: Optional[str] = None
    func: Any = None


@dataclass
class PluginInstallResultDTO:
    success: bool = False
    msg: str = ""


class PluginService:
    """插件业务服务"""

    def __init__(self,
                 plugin_manager: Optional[PluginManager] = None,
                 system_config: Optional[SystemConfig] = None,
                 plugin_helper: Optional[PluginHelper] = None):
        self._pm = plugin_manager or PluginManager()
        self._sys_conf = system_config or SystemConfig()
        self._helper = plugin_helper or PluginHelper()

    def update_plugin_config(self, plugin_id: str, config: dict) -> None:
        """保存插件配置并重新加载"""
        self._pm.save_plugin_config(pid=plugin_id, conf=config)
        self._pm.reload_plugin(plugin_id)

    def get_plugin_apps(self, user_level: int) -> PluginAppsDTO:
        """获取插件列表及统计信息"""
        plugins = self._pm.get_plugin_apps(user_level)
        statistic = self._helper.statistic()
        return PluginAppsDTO(plugins=plugins, statistic=statistic)

    def get_plugin_page(self, plugin_id: str) -> PluginPageDTO:
        """查询插件的额外数据"""
        title, content, func = self._pm.get_plugin_page(pid=plugin_id)
        return PluginPageDTO(title=title, content=content, func=func)

    def get_plugin_state(self, plugin_id: str):
        """获取插件状态"""
        return self._pm.get_plugin_state(plugin_id)

    def get_plugins_conf(self, user_level: int):
        """获取插件配置"""
        return self._pm.get_plugins_conf(user_level)

    def install_plugin(self, module_id: str, reload: bool = True) -> PluginInstallResultDTO:
        """安装插件"""
        if not module_id:
            return PluginInstallResultDTO(success=False, msg="参数错误")
        user_plugins: Any = self._sys_conf.get(SystemConfigKey.UserInstalledPlugins) or []
        if module_id not in user_plugins:
            user_plugins.append(module_id)
        self._sys_conf.set(SystemConfigKey.UserInstalledPlugins, user_plugins)
        if reload:
            self._pm.init_config()
        return PluginInstallResultDTO(success=True, msg="插件安装成功")

    def uninstall_plugin(self, module_id: str) -> PluginInstallResultDTO:
        """卸载插件"""
        if not module_id:
            return PluginInstallResultDTO(success=False, msg="参数错误")
        user_plugins: Any = self._sys_conf.get(SystemConfigKey.UserInstalledPlugins) or []
        if module_id in user_plugins:
            user_plugins.remove(module_id)
        self._sys_conf.set(SystemConfigKey.UserInstalledPlugins, user_plugins)
        self._pm.init_config()
        return PluginInstallResultDTO(success=True, msg="插件卸载成功")

    def run_plugin_method(self, plugin_id: str, method: str, kwargs: dict):
        """运行插件方法"""
        return self._pm.run_plugin_method(pid=plugin_id, method=method, **kwargs)
