"""Message services - 消息客户端、发送与命令处理."""

import json

from app.di import container
from app.events import Event
from app.events.constants import MESSAGE_INCOMING
from app.infrastructure.cache_system import TokenCache
from app.message import Message
from app.message.commands import COMMANDS
from app.schemas.system import SendMessageResultDTO
from app.services.sync_service import SyncService
from app.services.system.lifecycle import SystemLifecycleService
from app.services.torrentremover_core import TorrentRemoverService as TorrentRemover
from app.domain.enums import SearchType


class MessageClientService:
    """
    消息客户端业务服务
    负责消息客户端的增删改查、交互状态管理、连接测试
    """

    def __init__(self, message: Message | None = None):
        self._message = message or container.message()

    def delete_client(self, cid: int) -> bool:
        """删除消息客户端"""
        return bool(self._message.delete_message_client(cid=cid))

    def get_client(self, cid: int | None = None):
        """获取消息客户端信息"""
        return self._message.get_message_client_info(cid=cid)

    def toggle_interactive(self, cid: int, ctype: str, checked: bool) -> bool:
        """切换交互状态"""
        if checked:
            self._message.check_message_client(interactive=0, ctype=ctype)
        self._message.check_message_client(cid=cid, interactive=1 if checked else 0)
        return True

    def toggle_enable(self, cid: int, checked: bool) -> bool:
        """切换启用状态"""
        self._message.check_message_client(cid=cid, enabled=1 if checked else 0)
        return True

    def test_connection(self, ctype: str, config: dict) -> bool:
        """测试消息客户端连接"""
        return self._message.get_status(ctype=ctype, config=config)

    def upsert_client(
        self, name: str, cid: int, ctype: str, config: str, switchs, interactive: int, enabled: int, templates: str
    ) -> None:
        """添加或更新消息客户端"""
        parsed_switchs = switchs
        if isinstance(switchs, str):
            try:
                parsed_switchs = json.loads(switchs)
                if not isinstance(parsed_switchs, list):
                    parsed_switchs = []
            except json.JSONDecodeError:
                parsed_switchs = [s.strip() for s in switchs.split(",") if s.strip()]
        if not isinstance(parsed_switchs, list):
            parsed_switchs = []
        if cid:
            self._message.delete_message_client(cid=cid)
        if int(interactive) == 1:
            self._message.check_message_client(interactive=0, ctype=ctype)
        self._message.insert_message_client(
            name=name,
            ctype=ctype,
            config=config,
            switchs=parsed_switchs,
            interactive=interactive,
            enabled=enabled,
            templates=templates,
        )


class MessageSenderService:
    """
    消息发送业务服务
    """

    def __init__(self, message: Message | None = None):
        self._message = message or container.message()

    def send_custom_message(self, clients: list, title: str, text: str, image: str = "") -> SendMessageResultDTO:
        if not clients:
            return SendMessageResultDTO(success=False, message="未选择消息服务")
        self._message.send_custom_message(clients=clients, title=title, text=text, image=image)
        return SendMessageResultDTO(success=True)

    def send_plugin_message(self, title: str, text: str, image: str = "") -> SendMessageResultDTO:
        self._message.send_plugin_message(title=title, text=text, image=image)
        return SendMessageResultDTO(success=True)


class MessageCommandHandler:
    """
    消息命令处理器
    """

    def __init__(
        self,
        search_handler=None,
        torrent_remover=None,
        downloader=None,
        sync_svc=None,
        filetransfer=None,
        event_bus=None,
    ):
        self._search_handler = search_handler
        self._torrent_remover = torrent_remover
        self._downloader = downloader
        self._sync_svc = sync_svc
        self._filetransfer = filetransfer
        self._event_bus = event_bus or container.event_bus()
        self._commands = None

    @property
    def _command_map(self):
        if self._commands is None:
            self._commands = {
                "/ptr": {
                    "func": (self._torrent_remover or TorrentRemover()).auto_remove_torrents,
                    "desc": COMMANDS["/ptr"],
                },
                "/ptt": {"func": (self._downloader or container.downloader_core()).transfer, "desc": COMMANDS["/ptt"]},
                "/rst": {"func": (self._sync_svc or container.sync_service()).transfer_sync, "desc": COMMANDS["/rst"]},
                "/sub": {"func": container.subscription_monitor().run, "desc": COMMANDS.get("/sub", "订阅监控")},
                "/tbl": {
                    "func": (self._filetransfer or container.filetransfer_service()).truncate_transfer_blacklist,
                    "desc": COMMANDS["/tbl"],
                },
                "/trh": {"func": self._truncate_rsshistory, "desc": COMMANDS["/trh"]},
                "/utf": {"func": self._unidentification, "desc": COMMANDS["/utf"]},
                "/udt": {"func": SystemLifecycleService.restart_server, "desc": COMMANDS["/udt"]},
                "/sta": {"func": self._user_statistics, "desc": COMMANDS["/sta"]},
            }
        return self._commands

    def handle_message_job(self, msg, in_from=SearchType.OT, user_id=None, user_name=None):
        """处理消息事件"""
        if not msg:
            return

        self._event_bus.publish(
            Event(
                event_type=MESSAGE_INCOMING,
                payload={"channel": in_from.value, "user_id": user_id, "user_name": user_name, "message": msg},
            )
        )

        command = self._command_map.get(msg)
        if command:
            if func := command.get("func"):
                container.thread_executor().submit(func)
            container.message().send_channel_msg(
                channel=in_from, title="正在运行 {} ...".format(command.get("desc")), user_id=user_id or ""
            )
            return

        # 插件命令
        plugin_commands = container.message().get_plugin_commands()
        msg_list = msg.split(" ")
        cmd_key = msg_list[0]
        plugin_cmd = plugin_commands.get(cmd_key)
        if plugin_cmd:
            func = plugin_cmd.get("func")
            if func:
                container.thread_executor().submit(func, msg, in_from, user_id, user_name)
            container.message().send_channel_msg(
                channel=in_from, title="正在运行 {} ...".format(plugin_cmd.get("desc")), user_id=user_id or ""
            )
            return

        TokenCache.delete("search")
        if self._search_handler:
            container.thread_executor().submit(self._search_handler.handle, msg, in_from, user_id, user_name)

    @staticmethod
    def _truncate_rsshistory():
        container.rss_helper().truncate_rss_history()
        container.subscribe_service().truncate_rss_episodes()

    @staticmethod
    def _user_statistics():
        TokenCache.delete("statistics")
        container.site_userinfo().refresh_site_data_now()

    @staticmethod
    def _unidentification():
        from typing import cast

        item_ids = []
        records = container.filetransfer_service().get_transfer_unknown_paths()
        if not records:
            return
        for rec in records:
            if not cast(str, rec.PATH):
                continue
            item_ids.append(rec.ID)
        if len(item_ids) > 0:
            SyncService().re_identify_items(flag="unidentification", ids=item_ids)
