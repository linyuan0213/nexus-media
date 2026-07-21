"""企业微信消息客户端单元测试."""

import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.message.client.wechat import WeChat


def _make_encrypted_echostr(echostr: str, corpid: str, encoding_aes_key: str) -> str:
    """构造企业微信加密 echostr 用于测试."""
    key = base64.b64decode(encoding_aes_key + "=")
    iv = key[:16]
    random_bytes = os.urandom(16)
    msg_len = struct.pack(">I", len(echostr.encode("utf-8")))
    plaintext = random_bytes + msg_len + echostr.encode("utf-8") + corpid.encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("utf-8")


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


class TestWeChatVerifyUrl:
    """测试企业微信回调 URL 验证."""

    def test_verify_url_plaintext(self):
        """明文模式下验证 URL 成功返回 echostr."""
        client = WeChat({"token": "test_token", "corpid": "test_corpid"})
        timestamp = "1234567890"
        nonce = "nonce123"
        echostr = "hello_wechat"
        signature = hashlib.sha1("".join(sorted(["test_token", timestamp, nonce, echostr])).encode("utf-8")).hexdigest()
        result = client.verify_url(signature, timestamp, nonce, echostr)
        assert result == echostr.encode("utf-8")

    def test_verify_url_encrypted(self):
        """加密模式下验证 URL 成功返回解密后的 echostr."""
        corpid = "test_corpid"
        token = "test_token"
        encoding_aes_key = base64.b64encode(os.urandom(32)).decode("utf-8")[:43]
        echostr = "hello_wechat_encrypted"
        encrypted = _make_encrypted_echostr(echostr, corpid, encoding_aes_key)
        timestamp = "1234567890"
        nonce = "nonce123"
        signature = hashlib.sha1("".join(sorted([token, timestamp, nonce, encrypted])).encode("utf-8")).hexdigest()
        client = WeChat({"token": token, "corpid": corpid, "encodingAESKey": encoding_aes_key})
        result = client.verify_url(signature, timestamp, nonce, encrypted)
        assert result == echostr.encode("utf-8")

    def test_verify_url_invalid_signature(self):
        """签名错误时返回 None."""
        client = WeChat({"token": "test_token", "corpid": "test_corpid"})
        result = client.verify_url("bad_signature", "1234567890", "nonce123", "hello")
        assert result is None

    def test_verify_url_no_token(self):
        """未配置 token 时返回 None."""
        client = WeChat({"corpid": "test_corpid"})
        result = client.verify_url("signature", "1234567890", "nonce123", "hello")
        assert result is None


class TestWeChatParseMessage:
    """测试企业微信消息解析."""

    def test_parse_plaintext_message(self):
        """明文模式解析 XML 消息."""
        client = WeChat({"token": "test_token", "corpid": "test_corpid"})
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[toUser]]></ToUserName>"
            "<FromUserName><![CDATA[fromUser]]></FromUserName>"
            "<CreateTime>1348831860</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[hello]]></Content>"
            "<MsgId>1234567890123456</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        timestamp = "1234567890"
        nonce = "nonce123"
        signature = hashlib.sha1("".join(sorted(["test_token", timestamp, nonce])).encode("utf-8")).hexdigest()
        msg = client.parse_message(xml, signature=signature, timestamp=timestamp, nonce=nonce)
        assert msg is not None
        assert msg["FromUserName"] == "fromUser"
        assert msg["Content"] == "hello"

    def test_parse_encrypted_message(self):
        """加密模式解析 XML 消息."""
        corpid = "test_corpid"
        token = "test_token"
        encoding_aes_key = base64.b64encode(os.urandom(32)).decode("utf-8")[:43]
        inner_xml = (
            "<xml>"
            "<ToUserName><![CDATA[toUser]]></ToUserName>"
            "<FromUserName><![CDATA[fromUser]]></FromUserName>"
            "<Content><![CDATA[hello_enc]]></Content>"
            "</xml>"
        )
        encrypted = _make_encrypted_echostr(inner_xml, corpid, encoding_aes_key)
        outer_xml = f"<xml><Encrypt><![CDATA[{encrypted}]]></Encrypt></xml>"
        timestamp = "1234567890"
        nonce = "nonce123"
        signature = hashlib.sha1("".join(sorted([token, timestamp, nonce, encrypted])).encode("utf-8")).hexdigest()
        client = WeChat({"token": token, "corpid": corpid, "encodingAESKey": encoding_aes_key})
        msg = client.parse_message(outer_xml, signature=signature, timestamp=timestamp, nonce=nonce)
        assert msg is not None
        assert msg["FromUserName"] == "fromUser"
        assert msg["Content"] == "hello_enc"

    def test_parse_message_invalid_signature(self):
        """签名错误返回 None."""
        client = WeChat({"token": "test_token", "corpid": "test_corpid"})
        xml = "<xml><Content><![CDATA[hello]]></Content></xml>"
        msg = client.parse_message(xml, signature="bad", timestamp="1234567890", nonce="nonce")
        assert msg is None
