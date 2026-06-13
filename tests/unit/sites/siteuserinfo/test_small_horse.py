"""SmallHorse 站点用户信息解析单元测试."""

from app.sites.siteuserinfo import small_horse
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
        self.seeding = 0
        self.leeching = 0


class TestSmallHorse:
    def test_is_small_horse(self):
        ins = _MockInstance()
        ins._index_html = "<html>Small Horse</html>"
        assert small_horse.is_small_horse(ins) is True  # type: ignore[arg-type]

    def test_is_not_small_horse(self):
        ins = _MockInstance()
        ins._index_html = "<html>Other</html>"
        assert small_horse.is_small_horse(ins) is False  # type: ignore[arg-type]

    def test_parse(self):
        ins = _MockInstance()
        ins._index_html = """
        <html>
          <a href="user.php?id=12345">user</a>
          <ul class="stats nobullet"><li>ignore</li></ul>
          <ul class="stats nobullet">
            <li><span>2020-01-01</span></li>
            <li></li>
            <li>Upload: 100 GB</li>
            <li>Download: 50 GB</li>
            <li><span>2.0</span></li>
            <li>Bonus: 1234</li>
          </ul>
          <ul class="stats nobullet"><li>ignore</li></ul>
          <ul class="stats nobullet">
            <li>Level: VIP</li>
          </ul>
          <ul class="stats nobullet">
            <li></li><li></li><li></li><li></li><li></li><li></li><li>Leeching: 5</li>
          </ul>
        </html>
        """
        small_horse.parse(ins)  # type: ignore[arg-type]
        assert ins.userid == "12345"
        assert ins.username == "user"
        assert ins.user_level == "VIP"
        assert ins.upload > 0
        assert ins.download > 0
        assert ins.ratio == 2.0
        assert ins.bonus == 1234.0
        assert ins.leeching == 5

    def test_parse_empty_html(self):
        ins = _MockInstance()
        small_horse.parse(ins)  # type: ignore[arg-type]
        assert ins.userid is None
