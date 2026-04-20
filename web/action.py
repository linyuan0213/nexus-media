"""
WebAction 入口类新形态
仅保留：
1. 应用生命周期管理（start_service / stop_service / restart_server）
2. 消息命令处理（handle_message_job）—— 被 webhook / websocket 调用
3. 少量被模板过滤器直接引用的静态工具方法
"""
from app.services.system_service import (
    start_service, stop_service, restart_service, restart_server,
    MessageCommandHandler, get_commands, get_rmt_modes, parse_brush_rule_string
)
from web.core.action_utils import mediainfo_dict, delete_media_file, get_media_exists_info, set_config_value, set_config_directory


class WebAction:
    """
    仅保留生命周期管理与消息处理，以及向后兼容的静态工具方法引用。
    """

    @staticmethod
    def stop_service():
        stop_service()

    @staticmethod
    def start_service():
        start_service()

    @classmethod
    def restart_service(cls):
        restart_service()

    @classmethod
    def restart_server(cls):
        restart_server()

    @staticmethod
    def handle_message_job(msg, in_from=None, user_id=None, user_name=None):
        """处理消息事件"""
        if in_from is None:
            from app.utils.types import SearchType
            in_from = SearchType.OT
        MessageCommandHandler().handle_message_job(
            msg=msg, in_from=in_from, user_id=user_id, user_name=user_name
        )

    # 被模板过滤器 brush_rule_string 调用
    @staticmethod
    def parse_brush_rule_string(rules):
        return parse_brush_rule_string(rules)

    # 被 main.py 页面初始化调用
    @staticmethod
    def get_rmt_modes():
        return get_rmt_modes()

    @staticmethod
    def get_commands():
        return get_commands()

    # 向后兼容的静态工具方法（已迁移至 web.core.action_utils）
    mediainfo_dict = staticmethod(mediainfo_dict)
    delete_media_file = staticmethod(delete_media_file)
    get_media_exists_info = staticmethod(get_media_exists_info)
    set_config_value = staticmethod(set_config_value)
    set_config_directory = staticmethod(set_config_directory)
