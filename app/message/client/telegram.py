import contextlib
import time
from threading import Lock
from urllib.parse import urlencode

import requests

import log
from app.helper.thread_helper import ThreadHelper
from app.message import Message
from app.message.client._base import _IMessageClient
from app.message.schema import ConfigField, MessageConfigSchema
from app.services.apikey_service import APIKeyService
from app.utils import ExceptionUtils, RequestUtils
from app.utils.config_tools import get_domain, get_proxies
from config import Config

_webhook_lock = Lock()
_webhook_set = False


class Telegram(_IMessageClient):
    schema = "telegram"
    config_schema = MessageConfigSchema(
        name="Telegram",
        icon_url="/static/img/message/telegram.png",
        search_type="TG",
        fields=[
            ConfigField(
                id="token",
                required=True,
                title="Bot Token",
                tooltip="telegram机器人的Token，关注BotFather创建机器人",
                type="text",
            ),
            ConfigField(
                id="chat_id",
                required=True,
                title="Chat ID",
                tooltip="接受消息通知的用户、群组或频道Chat ID，关注@getidsbot获取",
                type="text",
            ),
            ConfigField(
                id="user_ids",
                required=False,
                title="User IDs",
                tooltip="允许使用交互的用户Chat ID，留空则只允许管理用户使用，关注@getidsbot获取",
                type="text",
                placeholder="使用,分隔多个Id",
            ),
            ConfigField(
                id="admin_ids",
                required=False,
                title="Admin IDs",
                tooltip="允许使用管理命令的用户Chat ID，关注@getidsbot获取",
                type="text",
                placeholder="使用,分隔多个Id",
            ),
            ConfigField(
                id="webhook",
                required=False,
                title="Webhook",
                tooltip="Telegram机器人消息有两种模式：Webhook或消息轮循；开启后将使用Webhook方式，需要在基础设置中正确配置好外网访问地址，同时受Telegram官方限制，外网访问地址需要设置为以下端口之一：443, 80, 88, 8443，且需要有公网认证的可信SSL证书；关闭后将使用消息轮循方式，使用该方式需要在基础设置->安全处将Telegram ipv4源地址设置为127.0.0.1，如同时使用了内置的SSL证书功能，消息轮循方式可能无法正常使用",
                type="switch",
            ),
        ],
    )
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
        self._admin_ids = cfg.get("admin_ids") or []
        self._user_ids = cfg.get("user_ids") or []
        self._domain = get_domain()
        self._api_key = APIKeyService().get_or_create_system_key("MessageWebhook")
        admin_ids = cfg.get("admin_ids")
        if admin_ids and not isinstance(admin_ids, list):
            self._admin_ids = [admin_ids]
        user_ids = cfg.get("user_ids")
        if user_ids and not isinstance(user_ids, list):
            self._user_ids = [user_ids]

    def _get_proxies(self):
        if self._proxy_event is not None:
            return self._proxy_event.wait(3)
        return get_proxies()

    def setup(self):
        if self.schema in Telegram._setup_done:
            return
        Telegram._setup_done.add(self.schema)
        if self.webhook:
            self._set_webhook()
        else:
            self._start_polling()
        # 菜单不再在 setup() 中设置，避免后台线程延迟执行覆盖插件命令
        # 统一由 Message.refresh_menus() 在系统启动完成后刷新

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not self.token or not self.chat_id or not self._enabled:
            return False, "参数未配置"
        if not title and not text:
            return False, "标题和内容不能同时为空"
        caption = f"*{title}*\n{text}" if title and text else title or text
        if not caption:
            return False, "消息内容为空"
        proxies = self._get_proxies()
        chat_ids = []
        if user_id and self.interactive:
            chat_ids = [user_id]
        else:
            chat_ids = self._user_ids + [self.chat_id]
        # 去重：避免同一 chat_id 在 user_ids 和 chat_id 中重复配置导致重复发送
        seen = set()
        unique_chat_ids = []
        for cid in chat_ids:
            if cid and cid not in seen:
                seen.add(cid)
                unique_chat_ids.append(cid)
        for chat_id in unique_chat_ids:
            if image:
                values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "Markdown"}
                url = f"https://api.telegram.org/bot{self.token}/sendPhoto?" + urlencode(values)
                res = RequestUtils(proxies=proxies).get_res(url)
                ok, msg = self._parse_response(res)
                if not ok:
                    return ok, msg
            else:
                values = {"chat_id": chat_id, "text": caption, "parse_mode": "Markdown"}
                url = f"https://api.telegram.org/bot{self.token}/sendMessage?" + urlencode(values)
                res = RequestUtils(proxies=proxies).get_res(url)
                ok, msg = self._parse_response(res)
                if not ok:
                    return ok, msg
        return True, ""

    def _parse_response(self, res):
        if not res or res.status_code != 200:
            return False, "网络请求失败"
        try:
            data = res.json()
            if data.get("ok"):
                return True, ""
            return False, data.get("description", "未知错误")
        except Exception:
            return False, "响应解析失败"

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
        return self.send_msg(title="", text=caption, image=image, user_id=chat_id)

    def _start_polling(self):
        if not self.token or not self._enabled:
            return
        ThreadHelper().start_thread(self._polling_loop, ())

    def _polling_loop(self):
        offset = 0
        while self._enabled:
            try:
                proxies = self._get_proxies()
                url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset={offset}&limit=10"
                res = RequestUtils(proxies=proxies, timeout=30).get_res(url)
                if res and res.status_code == 200:
                    data = res.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            offset = update.get("update_id", offset) + 1
                            self._process_update(update)
                time.sleep(2)
            except Exception as e:
                log.error(f"【Telegram】轮询异常: {e}")
                time.sleep(5)

    def _process_update(self, update):
        msg = update.get("message") or update.get("edited_message", {})
        text = msg.get("text", "")
        if not text:
            return
        user = msg.get("from", {})
        user_id = str(user.get("id", ""))
        if self._admin_ids and user_id not in self._admin_ids:
            return
        ds_url = f"http://127.0.0.1:{Config().get_config('app').get('web_port')}/telegram?apikey={self._api_key}"
        with contextlib.suppress(Exception):
            requests.post(ds_url, json=update, timeout=5)

    def _set_commands(self):
        if not self.token:
            log.warn("【Telegram】跳过设置菜单：token 为空")
            return
        try:
            commands = Message().get_commands()
            cmds = [{"command": k[1:], "description": v} for k, v in commands.items()]
            log.info(f"【Telegram】正在设置菜单，共 {len(cmds)} 个命令: {list(commands.keys())}")
            data = {"commands": cmds, "scope": {"type": "default"}}
            headers = {"content-type": "application/json"}
            res = requests.post(
                f"https://api.telegram.org/bot{self.token}/setMyCommands",
                json=data,
                headers=headers,
                proxies=get_proxies(),
                timeout=10,
            )
            if res and res.json().get("ok"):
                log.info(f"【Telegram】命令菜单已设置，共 {len(cmds)} 个")
            else:
                log.error("【Telegram】命令菜单设置失败：%s" % (res.json().get("description") if res else "网络错误"))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def refresh_menu(self):
        """刷新命令菜单（插件命令变更时调用）"""
        log.info("【Telegram】收到菜单刷新请求")
        self._set_commands()

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
        try:
            res = RequestUtils(proxies=get_proxies()).get_res(url)
            if res and res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    info = data.get("result", {})
                    if info.get("url") == self._webhook_url:
                        return 1
                    elif info.get("url"):
                        return 2
                    return 0
        except Exception:
            pass
        return 0

    def _del_webhook(self):
        url = f"https://api.telegram.org/bot{self.token}/deleteWebhook"
        try:
            res = RequestUtils(proxies=get_proxies()).get_res(url)
            if res and res.status_code == 200:
                log.info("【Telegram】Webhook 已删除")
        except Exception:
            pass


