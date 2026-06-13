"""Gazelle 站点用户信息解析单元测试."""

from app.sites.siteuserinfo import gazelle
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


class TestGazelle:
    def test_is_gazelle(self):
        ins = _MockInstance()
        ins._index_html = "<html>Powered by Gazelle</html>"
        assert gazelle.is_gazelle(ins) is True  # type: ignore[arg-type]

    def test_is_gazelle_dic_music(self):
        ins = _MockInstance()
        ins._index_html = "<html>DIC Music</html>"
        assert gazelle.is_gazelle(ins) is True  # type: ignore[arg-type]

    def test_is_not_gazelle(self):
        ins = _MockInstance()
        ins._index_html = "<html>Other</html>"
        assert gazelle.is_gazelle(ins) is False  # type: ignore[arg-type]

    def test_parse(self):
        ins = _MockInstance()
        ins._index_html = """
        <html>
          <a href="user.php?id=12345">user</a>
          <span id="header-uploaded-value" data-value="100 GB"></span>
          <span id="header-downloaded-value" data-value="50 GB"></span>
          <a href="bonus.php" data-tooltip="Bonus: 1,234.5">bonus</a>
          <span id="class-value" data-value="VIP"></span>
          <span id="join-date-value" data-value="2020-01-01"></span>
        </html>
        """
        gazelle.parse(ins)  # type: ignore[arg-type]
        assert ins.userid == "12345"
        assert ins.username == "user"
        assert ins.upload > 0
        assert ins.download > 0
        assert ins.bonus == 1234.5
        assert ins.user_level == "VIP"
        assert ins.join_at is not None

    def test_parse_fallback(self):
        ins = _MockInstance()
        ins._index_html = """
        <html>
          <a href="user.php?id=999">user2</a>
          <li id="stats_seeding"><span>200 GB</span></li>
          <li id="stats_leeching"><span>100 GB</span></li>
          <a href="bonus.php">2,000</a>
          <li>用户等级: Elite</li>
          <div class="box_userinfo_stats"><li>加入时间<span>2021-06-06</span></li></div>
        </html>
        """
        gazelle.parse(ins)  # type: ignore[arg-type]
        assert ins.userid == "999"
        assert ins.upload > 0
        assert ins.download > 0
        assert ins.bonus == 2000.0
        assert ins.user_level == "Elite"
        assert ins.join_at is not None

    def test_parse_empty_html(self):
        ins = _MockInstance()
        gazelle.parse(ins)  # type: ignore[arg-type]
        assert ins.userid is None
