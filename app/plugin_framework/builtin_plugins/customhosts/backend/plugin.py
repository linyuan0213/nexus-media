"""
CustomHosts Plugin v2
修改系统hosts文件，加速网络访问
"""

import os
import shutil
import time

from python_hosts import Hosts, HostsEntry

from app.plugin_framework.context import PluginContext
from app.utils import IpUtils, SystemUtils


class CustomHostsPlugin:
    """自定义Hosts插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("自定义Hosts插件已启用")
        self._apply_hosts()

    def on_disable(self):
        self.ctx.info("自定义Hosts插件已禁用")
        self._restore_hosts()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载hosts")
                self._apply_hosts()

    def _apply_hosts(self):
        config = self._get_config()
        enable = config.get("enable", False)
        hosts = config.get("hosts", "")

        if not enable:
            return

        if isinstance(hosts, str):
            hosts = hosts.split("\n")

        # 排除空行
        new_hosts = []
        for host in hosts:
            if host and host.strip():
                new_hosts.append(host.strip() + "\n")

        if not new_hosts:
            self.ctx.info("hosts配置为空")
            return

        error_flag, error_hosts = self._add_hosts_to_system(new_hosts)

        # 更新错误Hosts到配置
        self.ctx.set_config("err_hosts", error_hosts)
        self.ctx.set_config("enable", enable and not error_flag)

    def _restore_hosts(self):
        """禁用插件时恢复系统hosts"""
        system_hosts = self._read_system_hosts()
        orgin_entries = []
        for entry in system_hosts.entries:
            if entry.entry_type == "comment" and entry.comment == "# CustomHostsPlugin":
                break
            orgin_entries.append(entry)
        system_hosts.entries = orgin_entries
        try:
            system_hosts.write()
            self.ctx.info("已恢复系统hosts")
        except Exception as e:
            self.ctx.error(f"恢复系统hosts失败: {e}")

    @staticmethod
    def _read_system_hosts():
        if SystemUtils.is_windows():
            hosts_path = r"c:\windows\system32\drivers\etc\hosts"
        else:
            hosts_path = "/etc/hosts"
        return Hosts(path=hosts_path)

    def _add_hosts_to_system(self, hosts):
        system_hosts = self._read_system_hosts()

        # 过滤掉插件添加的hosts
        orgin_entries = []
        for entry in system_hosts.entries:
            if entry.entry_type == "comment" and entry.comment == "# CustomHostsPlugin":
                break
            orgin_entries.append(entry)
        system_hosts.entries = orgin_entries

        new_entrys = []
        err_hosts = []
        err_flag = False

        for host in hosts:
            if not host.strip():
                continue
            host_arr = str(host).split()
            try:
                host_entry = HostsEntry(
                    entry_type="ipv4" if IpUtils.is_ipv4(str(host_arr[0])) else "ipv6",
                    address=host_arr[0],
                    names=host_arr[1:],
                )
                new_entrys.append(host_entry)
            except Exception as err:
                err_hosts.append(host + "\n")
                self.ctx.error(f"{host} 格式转换错误：{str(err)}")

        if not new_entrys:
            return err_flag, err_hosts

        try:
            hosts_path = system_hosts.path
            if not os.access(hosts_path, os.W_OK):
                raise PermissionError(f"没有写入权限，请尝试: 1) 以管理员/root运行 2) 检查文件权限: ls -l {hosts_path}")

            # 创建备份
            backup_path = None
            try:
                system_backup = f"{hosts_path}.bak"
                if os.path.exists(hosts_path):
                    shutil.copy2(hosts_path, system_backup)
                    backup_path = system_backup
                    self.ctx.info(f"已创建hosts文件备份: {system_backup}")
            except Exception:
                try:
                    temp_dir = "/tmp" if not SystemUtils.is_windows() else os.getenv("TEMP") or "/tmp"
                    temp_backup = os.path.join(temp_dir, f"hosts_backup_{int(time.time())}.bak")
                    if os.path.exists(hosts_path):
                        shutil.copy2(hosts_path, temp_backup)
                        backup_path = temp_backup
                        self.ctx.warn(f"系统目录备份失败，已创建临时备份: {temp_backup}")
                except Exception as e:
                    self.ctx.error(f"创建备份失败: {str(e)}，将继续修改hosts但不创建备份")

            system_hosts.add([HostsEntry(entry_type="comment", comment="# CustomHostsPlugin")])
            system_hosts.add(new_entrys)
            system_hosts.write()
            self.ctx.info("更新系统hosts文件成功")
        except PermissionError as err:
            err_flag = True
            self.ctx.error(f"权限不足: {str(err)}")
        except Exception as err:
            err_flag = True
            self.ctx.error(f"更新系统hosts文件失败: {str(err)}")
            if backup_path and os.path.exists(backup_path):
                self.ctx.info("已恢复hosts文件备份")
                shutil.copy2(backup_path, hosts_path)

        return err_flag, err_hosts
