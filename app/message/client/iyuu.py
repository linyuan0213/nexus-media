from urllib.parse import urlencode

from app.message.client._base import _IMessageClient
from app.message.client_registry import ClientRegistry
from app.utils import ExceptionUtils, RequestUtils


class IyuuMsg(_IMessageClient):
    schema = "iyuu"

    def read_config(self):
        cfg = self._config or {}
        self._token = cfg.get("token")

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        if not self._token:
            return False, "参数未配置"
        try:
            sc_url = "http://iyuu.cn/%s.send?%s" % (self._token, urlencode({"text": title, "desp": text}))
            res = RequestUtils().get_res(sc_url)
            if res and res.status_code == 200:
                ret_json = res.json()
                errno = ret_json.get("errcode")
                error = ret_json.get("errmsg")
                if errno == 0:
                    return True, error
                else:
                    return False, error
            elif res is not None:
                return False, f"错误码：{res.status_code}，错误原因：{res.reason}"
            else:
                return False, "未获取到返回信息"
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list = None, user_id="", title="", **kwargs):
        pass


ClientRegistry.register(IyuuMsg)
