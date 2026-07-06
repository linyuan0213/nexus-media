"""
CustomHosts Plugin v3
应用层 DNS 映射，替代系统 /etc/hosts 修改。
无需 root 权限，仅对当前进程生效。
"""

from app.infrastructure.http import register_global_host_mapping
from app.plugin_framework.context import PluginContext


class CustomHostsPlugin:
    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("自定义Hosts插件已启用")
        self._apply_hosts()

    def on_disable(self):
        self.ctx.info("自定义Hosts插件已禁用")
        register_global_host_mapping({})

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
            register_global_host_mapping({})
            return

        if isinstance(hosts, str):
            hosts = hosts.strip().split("\n")

        mapping = {}
        for line in hosts:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                ip = parts[0]
                for domain in parts[1:]:
                    mapping[domain] = ip

        if not mapping:
            self.ctx.info("hosts配置为空")
            register_global_host_mapping({})
            return

        register_global_host_mapping(mapping)
        self.ctx.info(f"已加载 {len(mapping)} 条 DNS 映射")
