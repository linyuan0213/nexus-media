# -*- coding: utf-8 -*-
"""
SyncTimer Plugin v2
定时对同步目录进行整理
"""
from app.plugin_framework.context import PluginContext
from app.services.sync_core import SyncCore as Sync


class SyncTimerPlugin:
    """定时目录同步插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._sync = Sync()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("定时目录同步插件已启用")
        self._start_service()

    def on_disable(self):
        self.ctx.info("定时目录同步插件已禁用")
        self._stop_service()

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载服务")
                self._stop_service()
                self._start_service()

    def run(self):
        """立即运行同步"""
        self.ctx.info("手动触发同步")
        self._do_sync()

    def _start_service(self):
        config = self._get_config()
        cron = config.get("cron")

        if cron:
            self.ctx.info(f"目录定时同步服务启动，周期：{cron}")
            self.ctx.schedule_cron("sync", self._do_sync, cron=str(cron))

    def _stop_service(self):
        try:
            self.ctx.remove_schedule("sync")
        except Exception:
            pass

    def _do_sync(self):
        self.ctx.info("开始定时同步 ...")
        self._sync.transfer_sync()
        self.ctx.info("定时同步完成")
