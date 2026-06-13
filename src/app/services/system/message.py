"""Message services - 消息客户端、发送与命令处理."""

import json
from typing import cast

from app.domain.enums import SearchType
from app.events import Event
from app.events.constants import MESSAGE_INCOMING
from app.infrastructure.cache_system import TokenCache
from app.message import Message
from app.message.commands import COMMANDS
from app.schemas.system import SendMessageResultDTO


class MessageClientService:
    """
    消息客户端业务服务
    负责消息客户端的增删改查、交互状态管理、连接测试
    """

    def __init__(self, message: Message | None = None):
        self._message = message or Message()

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
        self._message = message or Message()

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
        thread_executor=None,
        message=None,
        subscription_monitor=None,
        rss_helper=None,
        subscribe_service=None,
        site_userinfo=None,
        sync_service=None,
    ):
        self._search_handler = search_handler
        self._torrent_remover = torrent_remover
        self._downloader = downloader
        self._sync_svc = sync_svc
        self._filetransfer = filetransfer
        self._event_bus = event_bus
        self._thread_executor = thread_executor
        self._message = message
        self._subscription_monitor = subscription_monitor
        self._rss_helper = rss_helper
        self._subscribe_service = subscribe_service
        self._site_userinfo = site_userinfo
        self._sync_service = sync_service
        self._commands = None

    @property
    def _command_map(self):
        if self._commands is None:
            self._commands = {
                "/ptr": {
                    "func": (self._torrent_remover.auto_remove_torrents if self._torrent_remover else lambda: None),
                    "desc": COMMANDS["/ptr"],
                },
                "/ptt": {
                    "func": self._downloader.transfer if self._downloader else lambda: None,
                    "desc": COMMANDS["/ptt"],
                },
                "/rst": {
                    "func": self._sync_svc.transfer_sync if self._sync_svc else lambda: None,
                    "desc": COMMANDS["/rst"],
                },
                "/sub": {
                    "func": self._subscription_monitor.run if self._subscription_monitor else lambda: None,
                    "desc": COMMANDS.get("/sub", "订阅监控"),
                },
                "/tbl": {
                    "func": self._filetransfer.truncate_transfer_blacklist if self._filetransfer else lambda: None,
                    "desc": COMMANDS.get("/tbl", "清理转移黑名单"),
                },
            }
        return self._commands

    def handle_message_job(self, msg, in_from=SearchType.OT, user_id=None, user_name=None):
        """处理消息事件"""
        if not msg:
            return

        if self._event_bus:
            self._event_bus.publish(
                Event(
                    event_type=MESSAGE_INCOMING,
                    payload={"channel": in_from.value, "user_id": user_id, "user_name": user_name, "message": msg},
                )
            )

        command = self._command_map.get(msg)
        if command:
            if func := command.get("func"):
                if self._thread_executor:
                    self._thread_executor.submit(func)
            if self._message:
                self._message.send_channel_msg(
                    channel=in_from, title="正在运行 {} ...".format(command.get("desc")), user_id=user_id or ""
                )
            return

        # 插件命令
        if self._message:
            plugin_commands = self._message.get_plugin_commands()
            msg_list = msg.split(" ")
            cmd_key = msg_list[0]
            plugin_cmd = plugin_commands.get(cmd_key)
            if plugin_cmd:
                func = plugin_cmd.get("func")
                if func and self._thread_executor:
                    self._thread_executor.submit(func, msg, in_from, user_id, user_name)
                self._message.send_channel_msg(
                    channel=in_from, title="正在运行 {} ...".format(plugin_cmd.get("desc")), user_id=user_id or ""
                )
                return

        TokenCache.delete("search")
        if self._search_handler and self._thread_executor:
            self._thread_executor.submit(self._search_handler.handle, msg, in_from, user_id, user_name)

    def _truncate_rsshistory(self):
        if self._rss_helper:
            self._rss_helper.truncate_rss_history()
        if self._subscribe_service:
            self._subscribe_service.truncate_rss_episodes()

    def _user_statistics(self):
        TokenCache.delete("statistics")
        if self._site_userinfo:
            self._site_userinfo.refresh_site_data_now()

    def _unidentification(self):
        item_ids = []
        if not self._filetransfer:
            return
        records = self._filetransfer.get_transfer_unknown_paths()
        if not records:
            return
        for rec in records:
            if not cast(str, rec.PATH):
                continue
            item_ids.append(rec.ID)
        if len(item_ids) > 0 and self._sync_service:
            self._sync_service.re_identify_items(flag="unidentification", ids=item_ids)
