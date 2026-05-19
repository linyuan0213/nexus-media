"""
rTorrent 下载器插件

启用时注册下载器到 Nexus Media 下载器注册表，
禁用时注销。
"""

from app.downloader.registry import get_client_class, register

from .client import Rtorrent


class RtorrentDownloaderPlugin:
    """rTorrent 下载器插件"""

    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        """启用时注册下载器"""
        try:
            register(Rtorrent)
            self.ctx.log_info("rTorrent 下载器已注册")
        except ValueError as e:
            self.ctx.log_warn(f"rTorrent 下载器注册失败: {e}")

    def on_disable(self):
        """禁用时注销下载器"""
        try:
            # 从注册表移除
            from app.downloader.registry import _registry

            if Rtorrent.client_id in _registry:
                del _registry[Rtorrent.client_id]
                self.ctx.log_info("rTorrent 下载器已注销")
        except Exception as e:
            self.ctx.log_warn(f"rTorrent 下载器注销失败: {e}")

    def on_hook(self, event, data):
        """事件处理"""
        if event == "plugin.config_changed" and data.get("plugin_id") == self.ctx.plugin_id:
            self.ctx.log_info("rTorrent 插件配置已更新")

    def get_status(self):
        """返回插件状态"""
        registered = get_client_class("rtorrent") is not None
        return {
            "plugin_id": self.ctx.plugin_id,
            "registered": registered,
            "client_name": Rtorrent.client_name,
        }
