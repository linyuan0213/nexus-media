

from flask_login import current_user

from app.conf import SystemConfig
from app.helper import PluginHelper
from app.plugins import PluginManager
from app.utils.types import SystemConfigKey
from web.actions._base import WebActionBase


class WebActionPluginMixin:
    @staticmethod
    def install_plugin(data, reload=True):
        """
        安装插件
        """
        module_id = data.get("id")
        if not module_id:
            return WebActionBase._fail(code=-1, msg="参数错误")
        # 用户已安装插件列表
        user_plugins = SystemConfig().get(SystemConfigKey.UserInstalledPlugins) or []
        if module_id not in user_plugins:
            user_plugins.append(module_id)
            # PluginHelper.install(module_id)
        # 保存配置
        SystemConfig().set(SystemConfigKey.UserInstalledPlugins, user_plugins)
        # 重新加载插件
        if reload:
            PluginManager().init_config()
        return WebActionBase._success(msg="插件安装成功")

    @staticmethod
    def uninstall_plugin(data):
        """
        卸载插件
        """
        module_id = data.get("id")
        if not module_id:
            return WebActionBase._fail(code=-1, msg="参数错误")
        # 用户已安装插件列表
        user_plugins = SystemConfig().get(SystemConfigKey.UserInstalledPlugins) or []
        if module_id in user_plugins:
            user_plugins.remove(module_id)
        # 保存配置
        SystemConfig().set(SystemConfigKey.UserInstalledPlugins, user_plugins)
        # 重新加载插件
        PluginManager().init_config()
        return WebActionBase._success(msg="插件卸载功")

    @staticmethod
    def get_plugin_apps():
        """
        获取插件列表
        """
        plugins = PluginManager().get_plugin_apps(current_user.level)
        statistic = PluginHelper.statistic()
        return WebActionBase._success(result=plugins, statistic=statistic)

    @staticmethod
    def get_plugin_page(data):
        """
        查询插件的额外数据
        """
        plugin_id = data.get("id")
        if not plugin_id:
            return WebActionBase._fail(msg="参数错误")
        title, content, func = PluginManager().get_plugin_page(pid=plugin_id)
        return WebActionBase._success(title=title, content=content, func=func)

    @staticmethod
    def get_plugin_state(data):
        """
        获取插件状态
        """
        plugin_id = data.get("id")
        if not plugin_id:
            return WebActionBase._fail(msg="参数错误")
        state = PluginManager().get_plugin_state(plugin_id)
        return WebActionBase._success(state=state)

    @staticmethod
    def get_plugins_conf():
        Plugins = PluginManager().get_plugins_conf(current_user.level)
        return WebActionBase._success(result=Plugins)

    @staticmethod
    def _update_plugin_config(data):
        """
        保存插件配置
        """
        plugin_id = data.get("plugin")
        config = data.get("config")
        if not plugin_id:
            return WebActionBase._fail(msg="数据错误")
        PluginManager().save_plugin_config(pid=plugin_id, conf=config)
        PluginManager().reload_plugin(plugin_id)
        return WebActionBase._success(msg="保存成功")

    @staticmethod
    def run_plugin_method(data):
        """
        运行插件方法
        """
        plugin_id = data.get("plugin_id")
        method = data.get("method")
        if not plugin_id or not method:
            return WebActionBase._fail(msg="参数错误")
        data.pop("plugin_id")
        data.pop("method")
        result = PluginManager().run_plugin_method(
            pid=plugin_id, method=method, **data)
        return WebActionBase._success(result=result)
