"""
CustomReleaseGroups Plugin v2
添加无法识别的制作组/字幕组
"""
from app.media import ReleaseGroupsMatcher
from app.plugin_framework.context import PluginContext


class CustomReleaseGroupsPlugin:
    """自定义制作组/字幕组插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._matcher = ReleaseGroupsMatcher()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("自定义制作组/字幕组插件已启用")
        self._load_config()

    def on_disable(self):
        self.ctx.info("自定义制作组/字幕组插件已禁用")

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载")
                self._load_config()

    def _load_config(self):
        config = self._get_config()
        custom_release_groups = config.get('release_groups')
        custom_separator = config.get('separator')

        if custom_release_groups:
            if custom_release_groups.startswith(';'):
                custom_release_groups = custom_release_groups[1:]
            if custom_release_groups.endswith(';'):
                custom_release_groups = custom_release_groups[:-1]
            custom_release_groups = custom_release_groups.replace(";", "|").replace("\n", "|")

        if custom_release_groups or custom_separator:
            if custom_release_groups:
                self.ctx.info("自定义制作组/字幕组已加载")
            if custom_separator:
                self.ctx.info(f"自定义分隔符 {custom_separator} 已加载")
            self._matcher.update_custom(custom_release_groups, custom_separator)
