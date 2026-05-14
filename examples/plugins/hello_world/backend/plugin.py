"""
Hello World 示例插件
展示插件框架 v2 的后端能力
"""


class HelloWorldPlugin:
    """Hello World 示例插件"""

    def __init__(self, ctx):
        self.ctx = ctx

    def on_enable(self):
        """启用时调用"""
        self.ctx.log_info("Hello World 插件已启用")
        greeting = self.ctx.get_config("greeting", "Hello!")
        self.ctx.notify("Hello World", f"插件已启用，当前问候语：{greeting}")

    def on_disable(self):
        """禁用时调用"""
        self.ctx.log_info("Hello World 插件已禁用")

    def on_hook(self, event, data):
        """事件处理"""
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                new_config = data.get("config", {})
                greeting = new_config.get("greeting", "Hello!")
                self.ctx.log_info(f"配置已更新，新问候语：{greeting}")

    def get_status(self):
        """自定义方法：返回插件状态"""
        return {
            "plugin_id": self.ctx.plugin_id,
            "greeting": self.ctx.get_config("greeting", "Hello!"),
            "data_dir": self.ctx.data_dir,
        }
