from pypushdeer import PushDeer

from app.message.client._base import _IMessageClient
from app.utils import StringUtils, ExceptionUtils
from app.message.client_registry import ClientRegistry


class PushDeerClient(_IMessageClient):
    schema = "pushdeer"

    def read_config(self):
        cfg = self._config or {}
        self._server = StringUtils.get_base_url(cfg.get('server'))
        self._apikey = cfg.get('apikey')

    def send_msg(self, title, text="", image="", url="", user_id=""):
        if not title and not text:
            return False, "标题和内容不能同时为空"
        try:
            if not self._server or not self._apikey:
                return False, "参数未配置"
            pushdeer = PushDeer(server=self._server, pushkey=self._apikey)
            res = pushdeer.send_markdown(title, desp=text)
            return (True, "成功") if res else (False, "失败")
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list = None, user_id="", title="", **kwargs):
        pass

ClientRegistry.register(PushDeerClient)
