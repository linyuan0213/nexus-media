"""Discuz 站点用户信息解析单元测试."""

from app.sites.siteuserinfo import discuz
from app.sites.siteuserinfo.config_html import ConfigHtmlUserInfo


class _MockInstance(ConfigHtmlUserInfo):
    def __init__(self):
        self._index_html = ""
        self.userid = None
        self.username = None
        self.user_level = None
        self.join_at = None
        self.bonus = 0.0
        self.upload = 0
        self.download = 0
        self.ratio = 0.0


class TestDiscuz:
    def test_is_discuz(self):
        ins = _MockInstance()
        ins._index_html = "<html>Powered by Discuz!</html>"
        assert discuz.is_discuz(ins) is True  # type: ignore[arg-type]

    def test_is_not_discuz(self):
        ins = _MockInstance()
        ins._index_html = "<html>Other</html>"
        assert discuz.is_discuz(ins) is False  # type: ignore[arg-type]

    def test_parse_user_info(self):
        ins = _MockInstance()
        ins._index_html = """
        <html>
          <a href="home.php?mod=space&amp;uid=12345">user</a>
          <a href="usergroup.php">Level1</a>
          <li><em>注册时间</em>2020-01-01 10:00</li>
          <li><em>积分</em>1,234.5</li>
          <li><em>上传量</em>100 GB / 200 GB</li>
          <li><em>下载量</em>50 GB / 100 GB</li>
        </html>
        """
        discuz.parse(ins)  # type: ignore[arg-type]
        assert ins.userid == "12345"
        assert ins.username == "user"
        assert ins.user_level == "Level1"
        assert ins.join_at is not None
        assert ins.bonus == 1234.5
        assert ins.upload > 0
        assert ins.download > 0
        assert ins.ratio == round(ins.upload / ins.download, 3)

    def test_parse_empty_html(self):
        ins = _MockInstance()
        discuz.parse(ins)  # type: ignore[arg-type]
        assert ins.userid is None
