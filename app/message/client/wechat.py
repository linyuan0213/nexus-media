import json
from datetime import datetime
from threading import Lock

import log
from app.message import Message
from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.message.commands import WECHAT_MENU, WECHAT_PLUGIN_GROUP
from app.utils import ExceptionUtils, RequestUtils

_menu_lock = Lock()


class WeChat(_IMessageClient):
    schema = "wechat"

    _send_msg_url = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=%s"
    _token_url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=%s&corpsecret=%s"
    _menu_url = "https://qyapi.weixin.qq.com/cgi-bin/menu/create?access_token=%s&agentid=%s"
    _proxy_url = ""
    _menu_done = set()

    def __init__(self, config):
        self.corpid = None
        self.corpsecret = None
        self.agent_id = None
        self.interactive = False
        self._use_proxy = False
        self._access_token = None
        self._expires_in = None
        self._token_time = None
        super().__init__(config)

    def read_config(self):
        cfg = self._config or {}
        self.corpid = cfg.get("corpid")
        self.corpsecret = cfg.get("corpsecret")
        self.agent_id = cfg.get("agentid")
        self.interactive = cfg.get("interactive", False)
        self._use_proxy = cfg.get("default_proxy", False)
        if self._use_proxy:
            base = self._use_proxy if isinstance(self._use_proxy, str) else self._proxy_url
            self._send_msg_url = f"{base}/cgi-bin/message/send?access_token=%s"
            self._token_url = f"{base}/cgi-bin/gettoken?corpid=%s&corpsecret=%s"
            self._menu_url = f"{base}/cgi-bin/menu/create?access_token=%s&agentid=%s"

    def setup(self):
        # 菜单不再在 setup() 中设置，避免后台线程延迟执行覆盖插件命令
        # 统一由 Message.refresh_menus() 在系统启动完成后刷新
        pass

    def stop(self):
        pass

    @classmethod
    def match(cls, ctype):
        return ctype == cls.schema

    def _get_access_token(self, force=False):
        need = False
        if not self._access_token or (datetime.now() - self._token_time).seconds >= (self._expires_in or 7200):
            need = True
        if not need and not force:
            return self._access_token
        if not self.corpid or not self.corpsecret:
            return None
        try:
            token_url = self._token_url % (self.corpid, self.corpsecret)
            res = RequestUtils().get_res(token_url)
            if res:
                data = res.json()
                if data.get("errcode") == 0:
                    self._access_token = data.get("access_token")
                    self._expires_in = data.get("expires_in")
                    self._token_time = datetime.now()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        return self._access_token

    def send_msg(self, title, text="", image="", url="", user_id=None):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        token = self._get_access_token()
        if not token:
            return False, "参数未配置或配置不正确"
        if image:
            return self._send_image(token, title, text, image, url, user_id)
        return self._send_text(token, title, text, url, user_id)

    def send_list_msg(self, medias: list, user_id="", title="", **kwargs):
        token = self._get_access_token()
        if not token:
            return False, "参数未配置或配置不正确"
        if not isinstance(medias, list):
            return False, "数据错误"
        message_url = self._send_msg_url % token
        if not user_id:
            user_id = "@all"
        articles = []
        for i, media in enumerate(medias):
            vote = media.get_vote_string()
            item_title = f"{i + 1}. {media.get_title_string()}"
            if vote:
                item_title = f"{item_title}\n{media.get_type_string()}，{vote}"
            else:
                item_title = f"{item_title}\n{media.get_type_string()}"
            articles.append(
                {
                    "title": item_title,
                    "description": "",
                    "picurl": media.get_message_image() if i == 0 else media.get_poster_image(),
                    "url": media.get_detail_url(),
                }
            )
        req = {"touser": user_id, "msgtype": "news", "agentid": self.agent_id, "news": {"articles": articles}}
        return self._post_request(message_url, req)

    def _send_text(self, token, title, text, url, user_id):
        message_url = self._send_msg_url % token
        content = f"{title}\n{text.replace(chr(10) + chr(10), chr(10))}" if text else title
        if url:
            content = f"{content}\n\n<a href='{url}'>查看详情</a>"
        if not user_id:
            user_id = "@all"
        req = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {"content": content},
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 0,
        }
        return self._post_request(message_url, req)

    def _send_image(self, token, title, text, image_url, url, user_id):
        message_url = self._send_msg_url % token
        if not user_id:
            user_id = "@all"
        req = {
            "touser": user_id,
            "msgtype": "news",
            "agentid": self.agent_id,
            "news": {
                "articles": [
                    {
                        "title": title,
                        "description": text.replace("\n\n", "\n") if text else "",
                        "picurl": image_url,
                        "url": url,
                    }
                ]
            },
        }
        return self._post_request(message_url, req)

    def _create_menu(self):
        if not self.agent_id:
            return
        with _menu_lock:
            if str(self.agent_id) in WeChat._menu_done:
                return
            token = self._get_access_token()
            if not token:
                log.error("【WeChat】无法获取access_token，菜单创建跳过")
                return
            try:
                commands = Message().get_commands()
                plugin_cmds = Message().get_plugin_commands()
                buttons = []
                for group in WECHAT_MENU:
                    subs = []
                    for cmd in group["commands"]:
                        name = commands.get(cmd, cmd)
                        if not name:
                            continue
                        subs.append({"type": "click", "name": name, "key": cmd.replace("/", "_")})
                    # 将插件命令追加到"管理"分组
                    if group["name"] == WECHAT_PLUGIN_GROUP and plugin_cmds:
                        for cmd, info in plugin_cmds.items():
                            if len(subs) >= 5:
                                break
                            subs.append({"type": "click", "name": info.get("desc", cmd), "key": cmd.replace("/", "_")})
                    if subs:
                        buttons.append({"name": group["name"], "sub_button": subs})
                if not buttons:
                    return
                log.info("【WeChat】正在创建菜单：%s" % json.dumps(buttons, ensure_ascii=False))
                data = json.dumps({"button": buttons}, ensure_ascii=False).encode("utf-8")
                headers = {"content-type": "application/json"}
                menu_url = self._menu_url % (token, self.agent_id)
                log.info("【WeChat】菜单请求URL: %s" % menu_url)
                res = RequestUtils(headers=headers).post(menu_url, data=data)
                if res and res.status_code == 200:
                    body = res.json()
                    if body.get("errcode") == 0:
                        WeChat._menu_done.add(str(self.agent_id))
                        log.info("【WeChat】应用菜单创建成功")
                    else:
                        log.error(
                            "【WeChat】菜单创建失败 errcode=%s errmsg=%s" % (body.get("errcode"), body.get("errmsg"))
                        )
                else:
                    log.error("【WeChat】菜单创建失败 HTTP=%s" % (res.status_code if res else "无响应"))
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【WeChat】菜单创建异常：%s" % e)

    def refresh_menu(self):
        """刷新命令菜单（插件命令变更时调用）"""
        WeChat._menu_done.discard(str(self.agent_id))
        self._create_menu()

    def _post_request(self, url, req_json):
        headers = {"content-type": "application/json"}
        try:
            data = json.dumps(req_json, ensure_ascii=False).encode("utf-8")
            log.debug("【WeChat】POST %s" % url.split("?")[0] if "?" in url else url)
            res = RequestUtils(headers=headers).post(url, data=data)
            if res and res.status_code == 200:
                body = res.json()
                if body.get("errcode") == 0:
                    return True, body.get("errmsg")
                if body.get("errcode") == 42001:
                    self._get_access_token(force=True)
                return False, body.get("errmsg")
            if res is not None:
                return False, f"错误码：{res.status_code}"
            return False, "未获取到返回信息"
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False, str(err)


ClientRegistry.register(WeChat)
