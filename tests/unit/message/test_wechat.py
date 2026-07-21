"""企业微信消息客户端单元测试."""

from app.message.client.wechat import WeChat


class TestWeChatProxyUrl:
    """测试企业微信代理地址规范化."""

    def test_proxy_url_without_scheme_gets_https(self):
        """缺少 scheme 的代理地址应自动补全为 https://"""
        client = WeChat({"default_proxy": "wecom.vivy.cc"})
        assert client._token_url == ("https://wecom.vivy.cc/cgi-bin/gettoken?corpid=%s&corpsecret=%s")
        assert client._send_msg_url == ("https://wecom.vivy.cc/cgi-bin/message/send?access_token=%s")

    def test_proxy_url_with_scheme_unchanged(self):
        """已包含 scheme 的代理地址应保持不变"""
        client = WeChat({"default_proxy": "http://wecom.vivy.cc"})
        assert client._token_url == ("http://wecom.vivy.cc/cgi-bin/gettoken?corpid=%s&corpsecret=%s")

    def test_proxy_url_with_trailing_slash_stripped(self):
        """代理地址末尾的斜杠应被去除，避免 URL 出现双斜杠"""
        client = WeChat({"default_proxy": "https://wecom.vivy.cc/"})
        assert client._token_url == ("https://wecom.vivy.cc/cgi-bin/gettoken?corpid=%s&corpsecret=%s")

    def test_no_proxy_uses_official_url(self):
        """未配置代理时使用企业微信官方地址"""
        client = WeChat({})
        assert client._token_url == ("https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=%s&corpsecret=%s")
