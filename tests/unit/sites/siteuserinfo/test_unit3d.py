"""Unit3d 站点用户信息解析单元测试."""

from unittest.mock import MagicMock

from lxml import etree

from app.sites.siteuserinfo import unit3d


class _MockInstance:
    def __init__(self):
        self._index_html = ""
        self._base_url_str = "https://example.com"
        self._fetch_html: MagicMock = MagicMock(return_value="")
        self.username = None
        self.user_level = None
        self.join_at = None
        self.bonus = 0.0
        self.upload = 0
        self.download = 0
        self.ratio = 0.0
        self.seeding = 0
        self.leeching = 0


class TestUnit3d:
    def test_is_unit3d(self):
        ins = _MockInstance()
        ins._index_html = "<script src='/js/unit3d.js'></script>"
        assert unit3d.is_unit3d(ins) is True  # type: ignore[arg-type]

    def test_is_not_unit3d(self):
        ins = _MockInstance()
        ins._index_html = "<html>Other</html>"
        assert unit3d.is_unit3d(ins) is False  # type: ignore[arg-type]

    def test_parse_index_page(self):
        ins = _MockInstance()
        ins._index_html = """
        <html>
          <div class="content">
            <a href="/users/alice/settings">settings</a>
            <span class="badge-user">Member</span>
            <a href="/bonus/earnings">1,234.5 BP</a>
            <h4>注册日期 2020-01-01</h4>
          </div>
        </html>
        """
        ins._fetch_html.return_value = """
        <html>
          <section>
            <h4>Upload</h4><span>100 GB</span>
          </section>
          <section>
            <h4>Download</h4><span>50 GB</span>
          </section>
          <section>
            <h4>Seeding</h4><span>10 seeding</span>
          </section>
          <section>
            <h4>Leeching</h4><span>2 leeching</span>
          </section>
        </html>
        """
        unit3d.parse(ins)  # type: ignore[arg-type]
        assert ins.username == "alice"
        assert ins.user_level == "Member"
        assert ins.bonus == 1234.5
        assert ins.join_at is not None
        assert ins.upload > 0
        assert ins.download > 0
        assert ins.seeding == 10
        assert ins.leeching == 2

    def test_parse_no_username(self):
        ins = _MockInstance()
        ins._index_html = "<html></html>"
        unit3d.parse(ins)  # type: ignore[arg-type]
        assert ins.username is None
        ins._fetch_html.assert_not_called()

    def test_extract_traffic_fallback(self):
        ins = _MockInstance()
        doc = etree.HTML("""
        <html>
          <span class="text-green">100 GB</span>
          <span class="text-red">50 GB</span>
        </html>
        """)
        unit3d._extract_traffic(ins, doc)  # type: ignore[arg-type]
        assert ins.upload > 0
        assert ins.download > 0

    def test_extract_seeding_icons(self):
        ins = _MockInstance()
        doc = etree.HTML("""
        <html>
          <div><i class="fa-arrow-up"></i><span>Seeding: 7</span></div>
          <div><i class="fa-arrow-down"></i><span>Leeching: 3</span></div>
        </html>
        """)
        unit3d._extract_seeding(ins, doc)  # type: ignore[arg-type]
        assert ins.seeding == 7
        assert ins.leeching == 3
