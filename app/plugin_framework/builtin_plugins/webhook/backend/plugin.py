"""
Webhook Plugin v2
事件发生时向第三方地址发送请求
"""
from app.plugin_framework.context import PluginContext
from app.utils import RequestUtils


class WebhookPlugin:
    """Webhook插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("Webhook插件已启用")

    def on_disable(self):
        self.ctx.info("Webhook插件已禁用")

    def on_hook(self, event, data):
        config = self._get_config()
        webhook_url = config.get("webhook_url")
        method = config.get("method", "post")

        if not webhook_url:
            return

        event_info = {
            "type": event,
            "data": data or {}
        }

        try:
            if method == 'post':
                ret = RequestUtils(content_type="application/json").post_res(webhook_url, json=event_info)
            else:
                ret = RequestUtils().get_res(webhook_url, params=event_info)

            if ret:
                self.ctx.info(f"Webhook发送成功：{webhook_url}")
            elif ret is not None:
                self.ctx.error(f"Webhook发送失败，状态码：{ret.status_code}，返回信息：{ret.text} {ret.reason}")
            else:
                self.ctx.error("Webhook发送失败，未获取到返回信息")
        except Exception as e:
            self.ctx.error(f"Webhook发送异常：{e}")
