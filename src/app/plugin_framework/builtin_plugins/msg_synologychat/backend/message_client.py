import threading
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import log
from app.core.settings import settings
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig
from app.message.client._base import _IMessageClient
from app.message.schema import ConfigField, MessageConfigSchema
from app.utils import ExceptionUtils, StringUtils
from app.utils.json_utils import JsonUtils

lock = threading.Lock()


class SynologyChat(_IMessageClient):
    schema = "synologychat"
    config_schema = MessageConfigSchema(
        name="Synology Chat",
        icon_url="/api/plugin-framework/plugins/msg_synologychat/assets/synologychat.png",
        search_type="SYNOLOGY",
        fields=[
            ConfigField(
                id="webhook_url",
                required=True,
                title="机器人传入URL",
                tooltip="在Synology Chat中创建机器人，获取机器人传入URL",
                type="text",
                placeholder="https://xxx/webapi/entry.cgi?api=xxx",
            ),
            ConfigField(
                id="token",
                required=True,
                title="令牌",
                tooltip="在Synology Chat中创建机器人，获取机器人令牌",
                type="text",
                placeholder="",
            ),
            ConfigField(
                id="verify_ssl",
                required=False,
                title="校验证书",
                tooltip="Synology 常用自签名证书或 IP 访问，默认跳过校验；使用可信证书时可开启",
                type="switch",
                default=False,
                advanced=True,
            ),
            ConfigField(
                id="webhook_ipv4",
                required=False,
                title="Webhook IPv4 白名单",
                tooltip="允许的 IPv4 地址段（CIDR），逗号分隔，默认 0.0.0.0/0 放行所有",
                type="text",
                placeholder="0.0.0.0/0",
                advanced=True,
            ),
            ConfigField(
                id="webhook_ipv6",
                required=False,
                title="Webhook IPv6 白名单",
                tooltip="允许的 IPv6 地址段（CIDR），逗号分隔，默认 ::/0 放行所有",
                type="text",
                placeholder="::/0",
                advanced=True,
            ),
        ],
    )
    _setup_done = set()
    # 机器人可见用户缓存与 autoblock 冷却，避免每次发送都调用 user_list
    _USERS_CACHE_TTL = 300
    _AUTOBLOCK_COOLDOWN = 300

    def __init__(self, config, apikey_service, message=None):
        self._config = settings
        self._domain = None
        self._webhook_url = None
        self._token = None
        self._req = HttpClient(
            config=HttpClientConfig(default_headers={"Content-Type": "application/x-www-form-urlencoded"})
        )
        self._apikey_service = apikey_service
        self._polling_stop = threading.Event()
        self._users_cache: list[int] = []
        self._users_cache_ts = 0.0
        self._autoblock_until = 0.0
        self._last_users_error = ""
        super().__init__(config, apikey_service, message=message)

    def read_config(self):
        cfg: Any = self._config or {}
        self._webhook_url = cfg.get("webhook_url")
        if self._webhook_url:
            self._domain = StringUtils.get_base_url(self._webhook_url)
        self._token = cfg.get("token")
        self._verify_ssl = bool(cfg.get("verify_ssl", False))
        self._req = HttpClient(
            config=HttpClientConfig(
                default_headers={"Content-Type": "application/x-www-form-urlencoded"},
                verify_ssl=self._verify_ssl,
            )
        )

    def setup(self):
        # Synology 传入 Webhook 仅用于“发送”，不支持轮询取消息；高频 GET 会触发 autoblock(105)。
        # 接收消息请把 Synology 的「传出URL」指向本插件的公开回调，此处不再启动轮询。
        log.info("SynologyChat 就绪（接收消息请配置传出URL回调，禁用传入URL轮询以规避 autoblock）")

    def stop_service(self):
        """停止服务（不再轮询传入URL）"""
        self._polling_stop.set()

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
                    return False, self._last_users_error or "机器人没有对任何用户可见"
            error_flag = True
            error_msg = ""
            for uid in user_ids:
                payload_data["user_ids"] = str(uid)
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
                    caption = (
                        f"{caption}\n{index}. <{media.get_detail_url()}|{media.get_title_string()}>\n"
                        f"{media.get_type_string()}，{media.get_vote_string()}"
                    )
                else:
                    caption = (
                        f"{caption}\n{index}. <{media.get_detail_url()}|{media.get_title_string()}>\n"
                        f"{media.get_type_string()}"
                    )
                index += 1
            if user_id:
                user_ids = [int(user_id)]
            else:
                user_ids = self.__get_bot_users()
                if not user_ids:
                    return False, self._last_users_error or "机器人没有对任何用户可见"
            error_flag = True
            error_msg = ""
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
        if not self._webhook_url:
            return []
        now = time.time()
        # autoblock 冷却期内直接复用缓存，避免继续请求加重封禁
        if now < self._autoblock_until:
            self._last_users_error = "Synology Chat 触发 autoblock(105)，请稍后再试"
            return self._users_cache
        # 命中缓存直接返回，减少 user_list 调用频率
        if self._users_cache and (now - self._users_cache_ts) < self._USERS_CACHE_TTL:
            return self._users_cache
        try:
            # 基于 webhook URL 本身构造 user_list 地址，保留路径前缀（兼容反向代理子路径），
            # 并优先使用 URL 内的 token（与机器人一致），避免单独配置的 token 不一致导致拿不到用户
            parsed = urlsplit(self._webhook_url)
            token = (parse_qs(parsed.query).get("token") or [None])[0] or self._token
            if not token:
                self._last_users_error = "Synology Chat 缺少 token"
                log.warn("[SynologyChat]缺少 token，无法获取机器人可见用户")
                return []
            base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            req_url = f"{base}?api=SYNO.Chat.External&method=user_list&version=2&token={quote(str(token))}"
            ret = self._req.get(url=req_url)
            body = ret.json()
            if not body or body.get("success") is False:
                error = body.get("error") or {} if isinstance(body, dict) else {}
                code = str(error.get("code") or "")
                detail = str(error.get("errors") or "")
                if code == "105" or "autoblock" in detail:
                    # 105 = autoblock：调用过于频繁被临时封禁；长冷却并提示根因
                    self._autoblock_until = now + self._AUTOBLOCK_COOLDOWN
                    self._last_users_error = (
                        "Synology Chat 接口返回 autoblock(105)：调用过于频繁被临时封禁。"
                        "请等待几分钟后重试；如启用轮询请降低频率，建议改用传出URL回调接收消息"
                    )
                    log.warn(f"[SynologyChat]触发 autoblock(105)，冷却 {self._AUTOBLOCK_COOLDOWN}s: {body}")
                else:
                    self._last_users_error = f"Synology Chat 获取可见用户失败: {body}"
                    log.warn(f"[SynologyChat]获取机器人可见用户失败: {body}")
                return []
            users = (body.get("data") or {}).get("users") or []
            user_ids = [user.get("user_id") for user in users if user.get("user_id")]
            if not user_ids:
                self._last_users_error = "机器人没有对任何用户可见"
                log.warn(
                    f"[SynologyChat]机器人当前没有对任何用户可见，请在 Synology Chat 中将该机器人添加/分享给用户；"
                    f"接口返回: {body}"
                )
                return []
            self._last_users_error = ""
            self._users_cache = user_ids
            self._users_cache_ts = now
            return user_ids
        except Exception as e:
            self._last_users_error = f"Synology Chat 获取可见用户异常: {e}"
            log.error(f"[SynologyChat]获取机器人可见用户异常: {e}")
            return []

    def __send_request(self, payload_data):
        payload = f"payload={JsonUtils.dumps(payload_data)}"
        if not self._webhook_url:
            return False, "未配置webhook"
        try:
            ret = self._req.post(url=self._webhook_url, data=payload)
            result = ret.json()
            if result:
                errno = result.get("error", {}).get("code")
                errmsg = result.get("error", {}).get("errors")
                if not errno:
                    return True, ""
                return False, f"{errno}-{errmsg}"
            return False, f"{ret.text}"
        except Exception:
            return False, "未获取到返回信息"
