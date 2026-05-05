# -*- coding: utf-8 -*-
"""
Customization Plugin v2
添加自定义占位符识别正则
"""
from app.media.meta.customization import CustomizationMatcher
from app.plugin_framework.context import PluginContext


class CustomizationPlugin:
    """自定义占位符插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._matcher = CustomizationMatcher()

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("自定义占位符插件已启用")
        self._load_config()

    def on_disable(self):
        self.ctx.info("自定义占位符插件已禁用")

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                self.ctx.info("配置已变更，重载")
                self._load_config()

    def _load_config(self):
        config = self._get_config()
        customization = config.get('customization')
        custom_separator = config.get('separator')

        if customization:
            customization = customization.replace("\n", ";").strip(";").split(";")
            customization = "|".join([f"({item})" for item in customization])
            if customization:
                self.ctx.info("自定义占位符已加载")
                if custom_separator:
                    self.ctx.info(f"自定义分隔符 {custom_separator} 已加载")
                self._matcher.update_custom(customization, custom_separator)
