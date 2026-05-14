import re
from threading import Lock

import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

import log
from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.services.apikey_service import APIKeyService
from app.utils import ExceptionUtils
from config import Config

lock = Lock()


class Slack(_IMessageClient):
    schema = "slack"

    def __init__(self, config):
        self._config = Config()
        self._interactive = False
        self._ds_url = None
        self._service = None
        self._channel = None
        self._client = None
        self._bot_token = None
        self._app_token = None
        super().__init__(config)

    def read_config(self):
        cfg = self._config or {}
        self._interactive = cfg.get("interactive", False)
        self._channel = cfg.get("channel") or "全体"
        self._bot_token = cfg.get("bot_token")
        self._app_token = cfg.get("app_token")

    def setup(self):
        _web_port = self._config.get_config("app").get("web_port")
        _api_key = APIKeyService().get_or_create_system_key("MessageWebhook")
        self._ds_url = f"http://127.0.0.1:{_web_port}/slack?apikey={_api_key}"
        if not self._bot_token:
            return
        try:
            slack_app = App(token=self._bot_token)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return
        self._client = slack_app.client

        @slack_app.event("message")
        def slack_message(message):
            local_res = requests.post(self._ds_url, json=message, timeout=10)
            log.debug(f"【Slack】message processed: {local_res.text}")

        @slack_app.action(re.compile(r"actionId-\d+"))
        def slack_action(ack, body):
            ack()
            local_res = requests.post(self._ds_url, json=body, timeout=60)
            log.debug(f"【Slack】action processed: {local_res.text}")

        @slack_app.event("app_mention")
        def slack_mention(say, body):
            say(f"收到，请稍等... <@{body.get('event', {}).get('user')}>")
            local_res = requests.post(self._ds_url, json=body, timeout=10)
            log.debug(f"【Slack】mention processed: {local_res.text}")

        @slack_app.shortcut(re.compile(r"/*"))
        def slack_shortcut(ack, body):
            ack()
            local_res = requests.post(self._ds_url, json=body, timeout=10)
            log.debug(f"【Slack】shortcut processed: {local_res.text}")

        if self._interactive and self._app_token:
            try:
                self._service = SocketModeHandler(slack_app, self._app_token)
                self._service.connect()
                log.info("Slack消息接收服务启动")
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error(f"Slack消息接收服务启动失败: {err}")

    def stop_service(self):
        if self._service:
            try:
                self._service.close()
            except Exception as err:
                print(str(err))
            log.info("Slack消息接收服务已停止")

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        if not self._client:
            return False, "消息客户端未就绪"
        try:
            channel = user_id or self.__find_public_channel()
            titles = str(title).split('\n')
            if len(titles) > 1:
                title = titles[0]
                text = "\n".join(titles[1:]) if not text else f"{chr(10).join(titles[1:])}\n{text}"
            block = {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{title}*\n{text}"}
            }
            if image:
                block['accessory'] = {"type": "image", "image_url": image, "alt_text": title}
            blocks = [block]
            if image and url:
                blocks.append({
                    "type": "actions",
                    "elements": [{
                        "type": "button",
                        "text": {"type": "plain_text", "text": "查看详情", "emoji": True},
                        "value": "click_me_url",
                        "url": url,
                        "action_id": "actionId-url"
                    }]
                })
            result = self._client.chat_postMessage(channel=channel, blocks=blocks)
            return True, result
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list, user_id="", title="", **kwargs):
        if not medias:
            return False, "参数有误"
        if not self._client:
            return False, "消息客户端未就绪"
        try:
            channel = user_id or self.__find_public_channel()
            title = title or f"共找到{len(medias)}条相关信息，请选择"
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}}]
            for i, media in enumerate(medias):
                blocks.append({"type": "divider"})
                idx = i + 1
                if media.get_star_string():
                    text = f"{idx}. *<{media.get_detail_url()}|{media.get_title_string()}>*\n{media.get_type_string()}\n{media.get_star_string()}\n{media.get_overview_string(50)}"
                else:
                    text = f"{idx}. *<{media.get_detail_url()}|{media.get_title_string()}>*\n{media.get_type_string()}\n{media.get_overview_string(50)}"
                if media.get_poster_image():
                    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text},
                        "accessory": {"type": "image", "image_url": media.get_poster_image(), "alt_text": media.get_title_string()}})
                else:
                    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
                blocks.append({"type": "actions", "elements": [{"type": "button",
                    "text": {"type": "plain_text", "text": "选择", "emoji": True},
                    "value": str(idx), "action_id": f"actionId-{idx}"}]})
            result = self._client.chat_postMessage(channel=channel, blocks=blocks)
            return True, result
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def __find_public_channel(self):
        if not self._client:
            return ""
        try:
            for result in self._client.conversations_list():
                for channel in result["channels"]:
                    if channel.get("name") == self._channel:
                        return channel.get("id")
        except SlackApiError as e:
            print(f"Slack Error: {e}")
        return ""

ClientRegistry.register(Slack)
