"""IpUtils 单元测试."""

from unittest.mock import patch

from app.utils.ip_utils import IpUtils


class TestIpUtils:
    def test_is_ipv4_valid(self):
        assert IpUtils.is_ipv4("192.168.1.1") is True
        assert IpUtils.is_ipv4("8.8.8.8") is True

    def test_is_ipv4_invalid(self):
        assert IpUtils.is_ipv4("256.1.1.1") is False
        assert IpUtils.is_ipv4("not_an_ip") is False
        assert IpUtils.is_ipv4("::1") is False

    def test_is_ipv6_valid(self):
        assert IpUtils.is_ipv6("::1") is True
        assert IpUtils.is_ipv6("fe80::1") is True

    def test_is_ipv6_invalid(self):
        assert IpUtils.is_ipv6("192.168.1.1") is False
        assert IpUtils.is_ipv6("not_an_ip") is False

    def test_is_ip(self):
        assert IpUtils.is_ip("192.168.1.1") is True
        assert IpUtils.is_ip("example.com") is False
        # is_ip uses inet_aton, which only supports IPv4
        assert IpUtils.is_ip("::1") is False

    def test_is_private_ip(self):
        assert IpUtils.is_private_ip("192.168.1.1") is True
        assert IpUtils.is_private_ip("10.0.0.1") is True
        assert IpUtils.is_private_ip("8.8.8.8") is False

    def test_is_private_ip_invalid(self):
        with patch("app.utils.ip_utils.log"):
            assert IpUtils.is_private_ip("not_an_ip") is False

    def test_is_internal_with_private_ip(self):
        assert IpUtils.is_internal("http://192.168.1.1:8080") is True

    def test_is_internal_with_public_ip(self):
        assert IpUtils.is_internal("http://8.8.8.8") is False

    def test_is_internal_domain(self):
        with patch("app.utils.ip_utils.socket.gethostbyname", return_value="127.0.0.1"):
            assert IpUtils.is_internal_domain("localhost") is True

    def test_is_internal_domain_lookup_fail(self):
        with patch("app.utils.ip_utils.socket.gethostbyname", side_effect=OSError):
            assert IpUtils.is_internal_domain("unknown.invalid") is False

    def test_is_internal_with_domain(self):
        with patch("app.utils.ip_utils.socket.gethostbyname", return_value="192.168.1.1"):
            assert IpUtils.is_internal("http://nas.local") is True

    def test_is_internal_with_public_domain(self):
        with patch("app.utils.ip_utils.socket.gethostbyname", return_value="8.8.8.8"):
            assert IpUtils.is_internal("http://google.com") is False
