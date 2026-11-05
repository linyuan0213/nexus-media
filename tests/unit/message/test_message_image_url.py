"""Web 消息图片代理：站内 /img 处理地址不再二次套代理."""

from app.message.web_store import _message_image_url


class TestMessageImageUrl:
    def test_relative_img_url_untouched(self):
        assert _message_image_url("/img/blur?url=https%3A%2F%2Fx") == "/img/blur?url=https%3A%2F%2Fx"

    def test_absolute_site_img_url_untouched(self):
        url = "https://nexus.firer.cc/img/crop?url=https%3A%2F%2Fx"
        assert _message_image_url(url) == url

    def test_external_image_is_proxied(self):
        result = _message_image_url("https://image.tmdb.org/t/p/w500/a.jpg")
        assert result.startswith("/img/")
