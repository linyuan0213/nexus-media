"""外部消息渠道图片代理测试."""

from app.message.core.dispatcher import MessageDispatcher


class _Client:
    def __init__(self):
        self.image = None

    def send_msg(self, title, text="", image="", url="", user_id="", content_profile="", msg_type=""):
        self.image = image
        return True, ""


def test_external_channel_uses_nexus_image_proxy():
    client = _Client()
    dispatcher = MessageDispatcher(None, None, domain="https://nexus.example")
    dispatcher._do_sendmsg(
        {"name": "飞书", "type": "feishu", "client": client},
        "入库",
        "test",
        "https://img3.doubanio.com/view/photo/m_ratio_poster/public/p1910931622.webp",
        "",
        "",
    )
    assert client.image is not None
    assert client.image.startswith("https://nexus.example/img/douban/")
    assert "img3.doubanio.com" in client.image


def test_web_channel_keeps_original_image():
    client = _Client()
    dispatcher = MessageDispatcher(None, None, domain="https://nexus.example")
    url = "https://img3.doubanio.com/view/photo/m_ratio_poster/public/p1910931622.webp"
    dispatcher._do_sendmsg(
        {"name": "内置消息页", "type": "web", "client": client},
        "入库",
        "test",
        url,
        "",
        "",
    )
    assert client.image == url
