"""
Webhook Plugin v2
事件发生时向第三方地址发送请求
"""

from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.infrastructure.http.exceptions import HttpClientError
from app.plugin_framework.context import PluginContext


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

        event_info = {"type": event, "data": data or {}}

        try:
            if method == "post":
                HttpClient(config=HttpClientConfig(default_headers={"Content-Type": "application/json"})).post(
                    webhook_url, json=event_info
                )
            else:
                HttpClient().get(webhook_url, params=event_info)
            self.ctx.info(f"Webhook发送成功：{webhook_url}")
        except HttpClientError as exc:
            self.ctx.error(f"Webhook发送失败，状态码：{exc.status_code}，返回信息：{exc.response_text}")
        except Exception as e:
            self.ctx.error(f"Webhook发送异常：{e}")
