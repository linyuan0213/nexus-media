from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.utils import ExceptionUtils, RequestUtils, StringUtils


class Gotify(_IMessageClient):
    schema = "gotify"

    def read_config(self):
        cfg = self._config or {}
        self._server = StringUtils.get_base_url(cfg.get('server'))
        self._token = cfg.get('token')
        try:
            self._priority = int(cfg.get('priority'))
        except Exception:
            self._priority = 8

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        try:
            if not self._server or not self._token:
                return False, "参数未配置"
            sc_url = "%s/message?token=%s" % (self._server, self._token)
            sc_data = {
                "title": title,
                "message": text,
                "priority": self._priority,
                "extras": {
                    "client::notification": {
                        "click": {"url": url}
                    },
                }
            }
            res = RequestUtils(content_type="application/json").post_res(sc_url, json=sc_data)
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

ClientRegistry.register(Gotify)
