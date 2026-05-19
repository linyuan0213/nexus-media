from app.message.registry import register

from .bark import Bark
from .chanify import Chanify
from .gotify import Gotify
from .iyuu import IyuuMsg
from .ntfy import Ntfy
from .pushdeer import PushDeerClient
from .pushplus import PushPlus
from .serverchan import ServerChan
from .slack import Slack
from .synologychat import SynologyChat
from .telegram import Telegram
from .webhook import Webhook
from .wechat import WeChat


def init_clients() -> None:
    """显式注册所有内置消息客户端。在应用启动时调用。"""
    register(Bark)
    register(Chanify)
    register(Gotify)
    register(IyuuMsg)
    register(Ntfy)
    register(PushDeerClient)
    register(PushPlus)
    register(ServerChan)
    register(Slack)
    register(SynologyChat)
    register(Telegram)
    register(WeChat)
    register(Webhook)
