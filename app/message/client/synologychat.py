import json
from threading import Lock
from urllib.parse import quote

import log
from app.helper.thread_helper import ThreadHelper
from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.services.apikey_service import APIKeyService
from app.utils import ExceptionUtils, RequestUtils, StringUtils
from config import Config

lock = Lock()


class SynologyChat(_IMessageClient):
    schema = "synologychat"
    _setup_done = set()

    def __init__(self, config):
        self._config = Config()
        self._interactive = False
        self._domain = None
        self._webhook_url = None
        self._token = None
        self._req = RequestUtils(content_type="application/x-www-form-urlencoded")
        super().__init__(config)

    def read_config(self):
        cfg = self._config or {}
        self._interactive = cfg.get("interactive", False)
        self._webhook_url = cfg.get("webhook_url")
        if self._webhook_url:
            self._domain = StringUtils.get_base_url(self._webhook_url)
        self._token = cfg.get("token")

    def setup(self):
        if self._interactive:
            if self._token and self._token in SynologyChat._setup_done:
                return
            SynologyChat._setup_done.add(self._token)
            _web_port = self._config.get_config("app").get("web_port")
            _api_key = APIKeyService().get_or_create_system_key("MessageWebhook")
            ds_url = f"http://127.0.0.1:{_web_port}/synologychat?apikey={_api_key}"
            ThreadHelper().start_thread(self._start_polling, (ds_url,))

    def _start_polling(self, ds_url):
        log.info("SynologyChat消息接收服务启动")
        while True:
            try:
                res = self._req.get_res(url=self._webhook_url)
                if res and res.status_code == 200:
                    data = res.json()
                    if data and "post_id" in data:
                        log.debug(f"【SynologyChat】接收到消息: {data}")
                        ThreadHelper().start_thread(self._process_message, (data, ds_url))
                import time

                time.sleep(2)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【SynologyChat】消息接收错误: {e}")
                import time

                time.sleep(5)

    def _process_message(self, data, ds_url):
        try:
            import requests

            requests.post(ds_url, json=data, timeout=10)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def check_token(self, token):
        return token == self._token

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        if not self._webhook_url or not self._token:
            return False, "参数未配置"
        try:
            titles = str(title).split("\n")
            if len(titles) > 1:
                title = titles[0]
                if not text:
                    text = "\n".join(titles[1:])
                else:
                    text = "{}\n{}".format("\n".join(titles[1:]), text)
            if text:
                caption = "*{}*\n{}".format(title, text.replace("\n\n", "\n"))
            else:
                caption = title
            if url and image:
                caption = f"{caption}\n\n<{url}|查看详情>"
            payload_data = {"text": quote(caption)}
            if image:
                payload_data["file_url"] = quote(image)
            if user_id:
                user_ids = [int(user_id)]
            else:
                user_ids = self.__get_bot_users()
                if not user_ids:
                    return False, "机器人没有对任何用户可见"
            for uid in user_ids:
                payload_data["user_ids"] = [uid]
                error_flag, error_msg = self.__send_request(payload_data)
                if not error_flag:
                    return error_flag, error_msg
            return error_flag, error_msg
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list, user_id="", title="", **kwargs):
        if not medias:
            return False, "参数有误"
        if not self._webhook_url or not self._token:
            return False, "参数未配置"
        try:
            if not title or not isinstance(medias, list):
                return False, "数据错误"
            index, image, caption = 1, "", f"*{title}*"
            for media in medias:
                if not image:
                    image = media.get_message_image()
                if media.get_vote_string():
                    caption = f"{caption}\n{index}. <{media.get_detail_url()}|{media.get_title_string()}>\n{media.get_type_string()}，{media.get_vote_string()}"
                else:
                    caption = f"{caption}\n{index}. <{media.get_detail_url()}|{media.get_title_string()}>\n{media.get_type_string()}"
                index += 1
            if user_id:
                user_ids = [int(user_id)]
            else:
                user_ids = self.__get_bot_users()
            for uid in user_ids:
                payload_data = {"text": quote(caption), "user_ids": [uid]}
                error_flag, error_msg = self.__send_request(payload_data)
                if not error_flag:
                    return error_flag, error_msg
            return error_flag, error_msg
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def __get_bot_users(self):
        if not self._domain or not self._token:
            return []
        req_url = (
            f"{self._domain}/webapi/entry.cgi?api=SYNO.Chat.External&method=user_list&version=2&token={self._token}"
        )
        ret = self._req.get_res(url=req_url)
        if ret and ret.status_code == 200:
            users = ret.json().get("data", {}).get("users", []) or []
            return [user.get("user_id") for user in users]
        return []

    def __send_request(self, payload_data):
        payload = f"payload={json.dumps(payload_data)}"
        ret = self._req.post_res(url=self._webhook_url, data=payload)
        if ret and ret.status_code == 200:
            result = ret.json()
            if result:
                errno = result.get("error", {}).get("code")
                errmsg = result.get("error", {}).get("errors")
                if not errno:
                    return True, ""
                return False, f"{errno}-{errmsg}"
            return False, f"{ret.text}"
        elif ret is not None:
            return False, f"错误码：{ret.status_code}，错误原因：{ret.reason}"
        return False, "未获取到返回信息"


ClientRegistry.register(SynologyChat)
