from threading import Event, Lock
from urllib.parse import urlencode

import requests

import log
from app.helper.thread_helper import ThreadHelper
from app.message.client._base import _IMessageClient
from app.message.commands import COMMANDS
from app.utils import RequestUtils, ExceptionUtils
from app.utils.config_tools import get_proxies
from config import Config
from app.utils.config_tools import get_domain, get_proxies
from app.message.client_registry import ClientRegistry


_webhook_lock = Lock()
_webhook_set = False


class Telegram(_IMessageClient):
    schema = "telegram"
    _setup_done = set()

    def __init__(self, config):
        self.token = None
        self.chat_id = None
        self.webhook = False
        self.interactive = False
        self._webhook_url = None
        self._admin_ids = []
        self._user_ids = []
        self._domain = None
        self._api_key = None
        self._enabled = True
        self._proxy_event = None
        super().__init__(config)

    def read_config(self):
        cfg = self._config or {}
        self.token = cfg.get("token")
        self.chat_id = cfg.get("chat_id")
        self.webhook = cfg.get("webhook", False)
        self.interactive = cfg.get("interactive", False)
        self._domain = get_domain()
        self._api_key = Config().get_config("security").get("api_key")
        admin_ids = cfg.get("admin_ids")
        self._admin_ids = [x.strip() for x in admin_ids.split(",")] if admin_ids else []
        self._user_ids = list(self._admin_ids)
        user_ids = cfg.get("user_ids")
        if user_ids:
            self._user_ids.extend(x.strip() for x in user_ids.split(",") if x.strip())

    def setup(self):
        if self.token and self.token in Telegram._setup_done:
            return
        Telegram._setup_done.add(self.token)
        ThreadHelper().start_thread(self._do_setup, ())

    def _do_setup(self):
        try:
            if self.webhook:
                if self._domain:
                    self._webhook_url = f"{self._domain}/telegram?apikey={self._api_key}"
                    self._set_webhook()
                if self._proxy_event:
                    self._proxy_event.set()
                    self._proxy_event = None
            elif self.interactive:
                self._del_webhook()
                if not self._proxy_event:
                    event = Event()
                    self._proxy_event = event
                    ThreadHelper().start_thread(self._start_polling, [event])
            self._set_commands()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def stop(self):
        self._enabled = False

    @classmethod
    def match(cls, ctype):
        return ctype == cls.schema

    def get_admin(self):
        return self._admin_ids

    def get_users(self):
        return self._user_ids

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        try:
            if not self.token or not self.chat_id:
                return False, "参数未配置"
            text = text.replace("[", r"\[").replace("_", r"\_").replace("*", r"\*").replace("`", r"\`")
            titles = str(title).split("\n")
            if len(titles) > 1:
                title = titles[0]
                extra = "\n".join(titles[1:])
                text = f"{extra}\n{text}" if text else extra
            caption = f"*{title}*\n{text.replace(chr(10) + chr(10), chr(10))}" if text else title
            if image and url:
                caption = f"{caption}\n\n[查看详情]({url})"
            chat_id = user_id or self.chat_id
            return self._send(chat_id, image, caption)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return False, str(e)

    def send_list_msg(self, medias: list, user_id="", title="", **kwargs):
        if not self.token or not self.chat_id:
            return False, "参数未配置"
        if not title or not isinstance(medias, list):
            return False, "数据错误"
        image = ""
        caption = f"*{title}*"
        for i, m in enumerate(medias):
            if not image:
                image = m.get_message_image()
            vote = m.get_vote_string()
            if vote:
                caption += f"\n{i + 1}. [{m.get_title_string()}]({m.get_detail_url()})\n{m.get_type_string()}，{vote}"
            else:
                caption += f"\n{i + 1}. [{m.get_title_string()}]({m.get_detail_url()})\n{m.get_type_string()}"
        chat_id = user_id or self.chat_id
        return self._send(chat_id, image, caption)

    def _send(self, chat_id, image, caption):
        def parse(res):
            if res and res.status_code == 200:
                j = res.json()
                return (True, "") if j.get("ok") else (False, j.get("description"))
            if res is not None:
                return False, f"错误码：{res.status_code}"
            return False, "未获取到返回信息"

        proxies = get_proxies()
        if image:
            values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "Markdown"}
            url = f"https://api.telegram.org/bot{self.token}/sendPhoto?" + urlencode(values)
            res = RequestUtils(proxies=proxies).get_res(url)
            ok, msg = parse(res)
            if ok:
                return ok, msg
            photo_res = RequestUtils(proxies=proxies).get_res(image)
            if photo_res and photo_res.content:
                url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
                res = requests.post(url, proxies=proxies, data=data, files={"photo": photo_res.content})
                ok, msg = parse(res)
                if ok:
                    return ok, msg
        values = {"chat_id": chat_id, "text": caption, "parse_mode": "Markdown"}
        url = f"https://api.telegram.org/bot{self.token}/sendMessage?" + urlencode(values)
        res = RequestUtils(proxies=proxies).get_res(url)
        return parse(res)

    def _set_commands(self):
        if not self.token:
            return
        try:
            cmds = [{"command": k[1:], "description": v} for k, v in COMMANDS.items()]
            data = {"commands": cmds, "scope": {"type": "default"}}
            headers = {"content-type": "application/json"}
            res = requests.post(
                f"https://api.telegram.org/bot{self.token}/setMyCommands",
                json=data, headers=headers, proxies=get_proxies(), timeout=10)
            if res and res.json().get("ok"):
                log.info(f"【Telegram】命令菜单已设置，共 {len(cmds)} 个")
            else:
                log.error("【Telegram】命令菜单设置失败：%s" % (res.json().get("description") if res else "网络错误"))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def _set_webhook(self):
        if not self._webhook_url:
            return
        with _webhook_lock:
            global _webhook_set
            if _webhook_set:
                return
            status = self._get_webhook_status()
            if not status or status == 1:
                _webhook_set = True
                return
            if status == 2:
                self._del_webhook()
            values = {"url": self._webhook_url, "allowed_updates": ["message"]}
            url = f"https://api.telegram.org/bot{self.token}/setWebhook?" + urlencode(values)
            res = RequestUtils(proxies=get_proxies()).get_res(url)
            if res and res.json().get("ok"):
                _webhook_set = True
                log.info(f"【Telegram】Webhook 设置成功：{self._webhook_url}")

    def _get_webhook_status(self):
        url = f"https://api.telegram.org/bot{self.token}/getWebhookInfo"
        res = RequestUtils(proxies=get_proxies()).get_res(url)
        if res and res.json() and res.json().get("ok"):
            result = res.json().get("result") or {}
            wh = result.get("url") or ""
            if wh == self._webhook_url:
                return 1
            if wh:
                return 2
            return 3
        return 0

    def _del_webhook(self):
        url = f"https://api.telegram.org/bot{self.token}/deleteWebhook"
        res = RequestUtils(proxies=get_proxies()).get_res(url)
        return bool(res and res.json() and res.json().get("ok"))

    def _start_polling(self, event):
        log.info("Telegram消息接收服务启动")
        timeout = 5
        offset = 0

        def consume(config, off, sc_url, ds_url):
            try:
                res = RequestUtils(proxies=get_proxies()).get_res(
                    f"{sc_url}{urlencode({'timeout': timeout, 'offset': off})}")
                if res and res.json():
                    for msg in res.json().get("result", []):
                        off = msg["update_id"] + 1
                        local = requests.post(ds_url, json=msg, timeout=10)
                        log.debug(f"【Telegram】msg processed: {local.text}")
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【Telegram】接收错误: {e}")
            return off

        while True:
            cfg = Config()
            web_port = cfg.get_config("app").get("web_port")
            sc_url = f"https://api.telegram.org/bot{self.token}/getUpdates?"
            ds_url = f"http://127.0.0.1:{web_port}/telegram?apikey={self._api_key}"
            if not self._enabled:
                log.info("Telegram消息接收服务已停止")
                break
            for _ in range(20):
                if event.is_set():
                    break
                offset = consume(cfg, offset, sc_url, ds_url)

ClientRegistry.register(Telegram)
