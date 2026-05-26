"""CommandManager - 消息命令注册与管理."""

from typing import Any

import log
from app.message.commands import COMMANDS


class CommandManager:
    """负责插件命令的注册、注销和菜单刷新."""

    def __init__(self, client_manager=None):
        self._client_manager = client_manager
        self._plugin_commands: dict = {}

    def register_command(self, cmd: str, desc: str, func: Any, plugin_id: str = "") -> None:
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        self._plugin_commands[cmd] = {"plugin_id": plugin_id, "desc": desc, "func": func}
        log.info(f"【Message】命令注册: {cmd} ({desc})")
        self._refresh_client_menus()

    def unregister_command(self, cmd: str) -> None:
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        if cmd in self._plugin_commands:
            del self._plugin_commands[cmd]
            log.info(f"【Message】命令注销: {cmd}")
            self._refresh_client_menus()

    def clear_plugin_commands(self, plugin_id: str) -> None:
        to_remove = [cmd for cmd, info in self._plugin_commands.items() if info.get("plugin_id") == plugin_id]
        for cmd in to_remove:
            del self._plugin_commands[cmd]
        if to_remove:
            log.info(f"【Message】插件 {plugin_id} 命令已清除: {to_remove}")
            self._refresh_client_menus()

    def get_commands(self) -> dict:
        all_cmds = dict(COMMANDS)
        for cmd, info in self._plugin_commands.items():
            all_cmds[cmd] = info.get("desc", "")
        return all_cmds

    def get_plugin_commands(self) -> dict:
        return self._plugin_commands.copy()

    def refresh_menus(self) -> None:
        self._refresh_client_menus()

    def _refresh_client_menus(self) -> None:
        if not self._client_manager:
            return
        self._client_manager._ensure_loaded()
        found = 0
        for client_entry in self._client_manager.active_clients:
            client = client_entry.get("client")
            ctype = client_entry.get("type", "unknown")
            if client and hasattr(client, "refresh_menu"):
                found += 1
                try:
                    client.refresh_menu()
                except Exception as e:
                    log.warn(f"【Message】刷新 {ctype} 菜单失败: {e}")
        if found:
            log.info(f"【Message】菜单刷新完成，{found} 个客户端已更新")
