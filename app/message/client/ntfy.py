from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.utils import ExceptionUtils, RequestUtils, StringUtils


class Ntfy(_IMessageClient):
    schema = "ntfy"

    def read_config(self):
        cfg = self._config or {}
        self._server = StringUtils.get_base_url(cfg.get("server"))
        self._token = cfg.get("token")
        self._topic = cfg.get("topic")
        self._tags = "rotating_light" if cfg.get("tags") == "" else (cfg.get("tags") or "rotating_light")
        self._tags = self._tags.split(",") if "," in self._tags else [self._tags]
        try:
            self._priority = int(cfg.get("priority"))
        except Exception:
            self._priority = 4

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        try:
            if not self._server or not self._token:
                return False, "参数未配置"
            sc_data = {
                "topic": self._topic,
                "title": title,
                "message": text,
                "priority": self._priority,
                "tags": self._tags,
            }
            res = RequestUtils(
                headers={"Authorization": "Bearer " + self._token}, content_type="application/json"
            ).post_res(self._server, json=sc_data)
            if res and res.status_code == 200:
                return True, "发送成功"
            elif res is not None:
                return False, f"错误码：{res.status_code}，错误原因：{res.reason}"
            else:
                return False, "未获取到返回信息"
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list = None, user_id="", title="", **kwargs):
        pass


ClientRegistry.register(Ntfy)
