"""消息客户端 — 内置客户端注册."""

from app.message.client.bark import Bark
from app.message.client.chanify import Chanify
from app.message.client.gotify import Gotify
from app.message.client.iyuu import IyuuMsg
from app.message.client.ntfy import Ntfy
from app.message.client.pushdeer import PushDeerClient
from app.message.client.pushplus import PushPlus
from app.message.client.serverchan import ServerChan
from app.message.client.slack import Slack
from app.message.client.synologychat import SynologyChat
from app.message.client.telegram import Telegram
from app.message.client.webhook import Webhook
from app.message.client.wechat import WeChat
from app.message.registry import register


def init_clients() -> None:
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
