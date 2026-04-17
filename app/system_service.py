import os
import shutil
import subprocess
import time
from pathlib import Path

import log
from app.brushtask_rule import BrushRuleEngine
from app.downloader import Downloader
from app.filetransfer import FileTransfer
from app.helper import RssHelper, ThreadHelper
from app.message import Message, MessageCenter
from app.plugins import PluginManager, EventManager
from app.rss import Rss
from app.sites import SiteUserInfo
from app.subscribe import Subscribe
from app.sync import Sync
from app.torrentremover import TorrentRemover
from app.utils import ExceptionUtils
from app.utils.types import SearchType, EventType
from web.backend.search_torrents import search_media_by_message
from web.cache import cache


def start_service():
    """启动服务"""
    from app.brushtask import BrushTask
    from app.helper import IndexerHelper
    from app.services.rss_service import RssTaskService as RssChecker
    from app.services.scheduler_core import SchedulerCore
    from app.sites import SiteConf
    IndexerHelper()
    SiteConf()
    SchedulerCore().start_service(load_defaults=True)
    Sync()
    BrushTask()
    RssChecker()
    TorrentRemover()
    PluginManager()


def stop_service():
    """关闭服务"""
    from app.brushtask import BrushTask
    from app.services.rss_service import RssTaskService as RssChecker
    from app.services.scheduler_core import SchedulerCore
    SchedulerCore().stop_service()
    Sync().stop_service()
    BrushTask().stop_service()
    RssChecker().stop_service()
    TorrentRemover().stop_service()
    Downloader().stop_service()
    PluginManager().stop_service()


def restart_service():
    """重启服务"""
    stop_service()
    start_service()


def restart_server():
    """停止进程"""
    stop_service()
    script_path = os.path.join(os.getcwd(), 'restart-server.sh')
    os.chmod(script_path, 0o755)
    res = subprocess.run(['bash', script_path], cwd=os.getcwd())
    if res.returncode == 0:
        log.info("Nastool 重启成功...")
    else:
        log.info(f"Nastool 重启失败: {res.stderr.decode()}")


class MessageCommandHandler:
    def __init__(self):
        self._commands = {
            "/ptr": {"func": TorrentRemover().auto_remove_torrents, "desc": "自动删种"},
            "/ptt": {"func": Downloader().transfer, "desc": "下载文件转移"},
            "/rst": {"func": Sync().transfer_sync, "desc": "目录同步"},
            "/rss": {"func": Rss().rssdownload, "desc": "电影/电视剧订阅"},
            "/ssa": {"func": Subscribe().subscribe_search_all, "desc": "订阅搜索"},
            "/tbl": {"func": FileTransfer().truncate_transfer_blacklist, "desc": "清理转移缓存"},
            "/trh": {"func": self._truncate_rsshistory, "desc": "清理RSS缓存"},
            "/utf": {"func": self._unidentification, "desc": "重新识别"},
            "/udt": {"func": restart_server, "desc": "系统更新"},
            "/sta": {"func": self._user_statistics, "desc": "站点数据统计"},
        }

    def handle_message_job(self, msg, in_from=SearchType.OT, user_id=None, user_name=None):
        """处理消息事件"""
        if not msg:
            return

        EventManager().send_event(EventType.MessageIncoming, {
            "channel": in_from.value,
            "user_id": user_id,
            "user_name": user_name,
            "message": msg
        })

        command = self._commands.get(msg)
        if command:
            ThreadHelper().start_thread(command.get("func"), ())
            Message().send_channel_msg(
                channel=in_from, title="正在运行 %s ..." % command.get("desc"), user_id=user_id)
            return

        plugin_commands = PluginManager().get_plugin_commands()
        msg_list = msg.split(" ")
        for command in plugin_commands:
            if command.get("cmd") == msg_list[0]:
                event_data = command.get("data") or {
                    "msg": msg_list[0] if len(msg_list) == 1 else msg_list[1]}
                EventManager().send_event(command.get("event"), event_data)
                Message().send_channel_msg(
                    channel=in_from, title="正在运行 %s ..." % command.get("desc"), user_id=user_id)
                return

        cache.delete("search")
        ThreadHelper().start_thread(search_media_by_message,
                                    (msg, in_from, user_id, user_name))

    @staticmethod
    def _truncate_rsshistory():
        RssHelper().truncate_rss_history()
        Subscribe().truncate_rss_episodes()

    @staticmethod
    def _user_statistics():
        cache.delete("statistics")
        SiteUserInfo().refresh_site_data_now()

    @staticmethod
    def _unidentification():
        from web.controllers.sync import re_identification
        ItemIds = []
        Records = FileTransfer().get_transfer_unknown_paths()
        for rec in Records:
            if not rec.PATH:
                continue
            ItemIds.append(rec.ID)
        if len(ItemIds) > 0:
            re_identification({"flag": "unidentification", "ids": ItemIds})


def get_commands():
    """获取命令列表"""
    handler = MessageCommandHandler()
    return [{
        "id": cid,
        "name": cmd.get("desc")
    } for cid, cmd in handler._commands.items()] + [{
        "id": item.get("cmd"),
        "name": item.get("desc")
    } for item in PluginManager().get_plugin_commands()]


def get_rmt_modes():
    from app.conf import ModuleConf
    from app.utils import SystemUtils
    RmtModes = ModuleConf.RMT_MODES_LITE if SystemUtils.is_lite_version(
    ) else ModuleConf.RMT_MODES
    return [{
        "value": value,
        "name": name.value
    } for value, name in RmtModes.items()]


def get_system_message(lst_time):
    messages = MessageCenter().get_system_messages(lst_time=lst_time)
    if messages:
        lst_time = messages[0].get("time")
    return {"code": 0, "message": messages, "lst_time": lst_time}


def parse_brush_rule_string(rules):
    return BrushRuleEngine.format_rule_html(rules)


def backup(full_backup=False, bk_path=None):
    """
    @param full_backup  是否完整备份（保留参数兼容性，当前始终完整备份）
    @param bk_path     自定义备份路径
    """
    from config import Config
    from app.db.database_factory import DatabaseFactory
    from app.db.migrate import export_to_file

    try:
        config_path = Path(Config().get_config_path())
        backup_file = f"bk_{time.strftime('%Y%m%d%H%M%S')}"
        if bk_path:
            backup_path = Path(bk_path) / backup_file
        else:
            backup_path = config_path / "backup_file" / backup_file
        backup_path.mkdir(parents=True)
        shutil.copy(f'{config_path}/config.yaml', backup_path)
        shutil.copy(f'{config_path}/default-category.yaml', backup_path)

        db_type = DatabaseFactory._get_config_db_type()
        engine = DatabaseFactory.create_engine()
        if db_type == DatabaseFactory.SQLITE:
            shutil.copy(f'{config_path}/user.db', backup_path)
        export_to_file(engine, str(backup_path / 'user_db_export.json'))
        engine.dispose()

        zip_file = str(backup_path) + '.zip'
        if os.path.exists(zip_file):
            zip_file = str(backup_path) + '.zip'
        shutil.make_archive(str(backup_path), 'zip', str(backup_path))
        shutil.rmtree(str(backup_path))
        return zip_file
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return None
