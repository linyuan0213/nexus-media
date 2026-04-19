from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from flask_login import current_user
from app.services.plugin_service import PluginService

plugin_bp = Blueprint("plugin", __name__, url_prefix="/api/web/plugin")


@plugin_bp.route('/update_plugin_config', methods=['POST'])
@any_auth
@parse_json_data
def _update_plugin_config(data):
    """
    保存插件配置
    """
    plugin_id = data.get("plugin")
    config = data.get("config")
    if not plugin_id:
        return fail(msg="数据错误")
    PluginService().update_plugin_config(plugin_id=plugin_id, config=config)
    return success(msg="保存成功")


@plugin_bp.route('/get_plugin_apps', methods=['POST'])
@any_auth
@parse_json_data
def get_plugin_apps(data):
    """
    获取插件列表
    """
    dto = PluginService().get_plugin_apps(current_user.level)
    return success(result=dto.plugins, statistic=dto.statistic)


@plugin_bp.route('/get_plugin_page', methods=['POST'])
@any_auth
@parse_json_data
def get_plugin_page(data):
    """
    查询插件的额外数据
    """
    plugin_id = data.get("id")
    if not plugin_id:
        return fail(msg="参数错误")
    dto = PluginService().get_plugin_page(plugin_id)
    return success(title=dto.title, content=dto.content, func=dto.func)


@plugin_bp.route('/get_plugin_state', methods=['POST'])
@any_auth
@parse_json_data
def get_plugin_state(data):
    """
    获取插件状态
    """
    plugin_id = data.get("id")
    if not plugin_id:
        return fail(msg="参数错误")
    state = PluginService().get_plugin_state(plugin_id)
    return success(state=state)


@plugin_bp.route('/get_plugins_conf', methods=['POST'])
@any_auth
@parse_json_data
def get_plugins_conf(data):
    Plugins = PluginService().get_plugins_conf(current_user.level)
    return success(result=Plugins)


@plugin_bp.route('/install_plugin', methods=['POST'])
@any_auth
@parse_json_data
def install_plugin(data, reload=True):
    """
    安装插件
    """
    module_id = data.get("id")
    dto = PluginService().install_plugin(module_id, reload=reload)
    if not dto.success:
        return fail(code=-1, msg=dto.msg)
    return success(msg=dto.msg)


@plugin_bp.route('/run_plugin_method', methods=['POST'])
@any_auth
@parse_json_data
def run_plugin_method(data):
    """
    运行插件方法
    """
    plugin_id = data.get("plugin_id")
    method = data.get("method")
    if not plugin_id or not method:
        return fail(msg="参数错误")
    data.pop("plugin_id")
    data.pop("method")
    result = PluginService().run_plugin_method(
        plugin_id=plugin_id, method=method, kwargs=data)
    return success(result=result)


@plugin_bp.route('/uninstall_plugin', methods=['POST'])
@any_auth
@parse_json_data
def uninstall_plugin(data):
    """
    卸载插件
    """
    module_id = data.get("id")
    dto = PluginService().uninstall_plugin(module_id)
    if not dto.success:
        return fail(code=-1, msg=dto.msg)
    return success(msg=dto.msg)
