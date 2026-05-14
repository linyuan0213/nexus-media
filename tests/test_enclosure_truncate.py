"""
Enclosure 截断单元测试 — 验证磁力链接 tracker 截断
"""

import sys
from unittest.mock import MagicMock

sys.modules["log"] = MagicMock()


def _truncate_enclosure(enclosure):
    """复现 repository 中的截断逻辑"""
    if enclosure and enclosure.startswith("magnet:"):
        return enclosure.split("&")[0]
    elif enclosure and len(enclosure) > 4000:
        return enclosure[:4000]
    return enclosure


class TestEnclosureTruncate:
    def test_magnet_truncate(self):
        """磁力链接应截断到只有 btih"""
        magnet = "magnet:?xt=urn:btih:ABC123&dn=test&tr=http://tracker1/announce&tr=http://tracker2/announce"
        result = _truncate_enclosure(magnet)
        assert result == "magnet:?xt=urn:btih:ABC123"
        assert "&tr=" not in result

    def test_http_url_unchanged(self):
        """HTTP URL 不应被截断"""
        url = "https://example.com/file.torrent"
        result = _truncate_enclosure(url)
        assert result == url

    def test_long_http_truncated(self):
        """超长 HTTP URL 应截断到 4000"""
        url = "https://example.com/" + "a" * 5000
        result = _truncate_enclosure(url)
        assert len(result) == 4000

    def test_none_enclosure(self):
        """None 应返回 None"""
        assert _truncate_enclosure(None) is None

    def test_short_magnet_unchanged(self):
        """短磁力链接无 tracker 应不变"""
        magnet = "magnet:?xt=urn:btih:ABC123"
        result = _truncate_enclosure(magnet)
        assert result == magnet
