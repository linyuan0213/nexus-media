import time
from urllib.parse import urlencode

from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.utils import ExceptionUtils, RequestUtils


class PushPlus(_IMessageClient):
    schema = "pushplus"

    def read_config(self):
        cfg = self._config or {}
        self._token = cfg.get('token')
        self._topic = cfg.get('topic')
        self._channel = cfg.get('channel')
        self._webhook = cfg.get('webhook')

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        if not text:
            text = "无"
        if not self._token or not self._channel:
            return False, "参数未配置"
        try:
            values = {
                "token": self._token,
                "channel": self._channel,
                "topic": self._topic,
                "webhook": self._webhook,
                "title": title,
                "content": text,
                "timestamp": time.time_ns() + 60
            }
            sc_url = "http://www.pushplus.plus/send?%s" % urlencode(values)
            res = RequestUtils().get_res(sc_url)
            if res and res.status_code == 200:
                ret_json = res.json()
                code = ret_json.get("code")
                msg = ret_json.get("msg")
                if code == 200:
                    return True, msg
                else:
                    return False, msg
            elif res is not None:
                return False, f"错误码：{res.status_code}，错误原因：{res.reason}"
            else:
                return False, "未获取到返回信息"
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list = None, user_id="", title="", **kwargs):
        pass

ClientRegistry.register(PushPlus)
