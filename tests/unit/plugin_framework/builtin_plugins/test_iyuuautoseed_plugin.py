"""IYUU自动辅种插件单元测试."""

from typing import cast
from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.iyuuautoseed.backend.iyuu.iyuu_helper import (
    IyuuHelper,
)
from app.plugin_framework.builtin_plugins.iyuuautoseed.backend.plugin import (
    IYUUAutoSeedPlugin,
)
from app.schemas.download import Torrent, TorrentStatus

MODULE = "app.plugin_framework.builtin_plugins.iyuuautoseed.backend.plugin"


def _make_plugin():
    plugin = IYUUAutoSeedPlugin.__new__(IYUUAutoSeedPlugin)
    plugin.ctx = MagicMock()
    plugin._downloader = MagicMock()
    plugin._sites = MagicMock()
    plugin.iyuuhelper = MagicMock()
    plugin._recheck_torrents = {}
    plugin._torrent_tags = ["已整理", "辅种"]
    plugin.total = plugin.realtotal = plugin.success = 0
    plugin.exist = plugin.fail = plugin.cached = 0
    return plugin


def _mock_helper(plugin) -> MagicMock:
    return cast(MagicMock, plugin.iyuuhelper)


def _mock_ctx(plugin) -> MagicMock:
    return cast(MagicMock, plugin.ctx)


def _torrent(progress=100, status=TorrentStatus.Paused):
    t = Torrent()
    t.id = "abc123"
    t.progress = progress
    t.status = status
    return t


class TestBuildDownloadUrl:
    def test_nexusphp_strips_passkey_placeholder(self):
        url = IYUUAutoSeedPlugin._build_download_url(2, "pt.example.com", "download.php?id={}&passkey={passkey}", 12345)
        assert url == "https://pt.example.com/download.php?id=12345"

    def test_strips_uid_and_hash_placeholders(self):
        url = IYUUAutoSeedPlugin._build_download_url(
            1, "www.hddolby.com", "download.php?id={}&uid={uid}&hash={hash}", 999
        )
        assert url == "https://www.hddolby.com/download.php?id=999"

    def test_http_scheme_when_is_https_zero(self):
        url = IYUUAutoSeedPlugin._build_download_url(
            0, "www.hdroute.org", "download.php?id={}&passkey={passkey}&from=rss", 42
        )
        assert url == "http://www.hdroute.org/download.php?id=42&from=rss"

    def test_path_placeholder_returns_none(self):
        # ttg 的 dl/{}/{passkey} 路径占位符无法剥离
        assert IYUUAutoSeedPlugin._build_download_url(2, "totheglory.im", "dl/{}/{passkey}", 123) is None

    def test_no_credential_placeholder(self):
        url = IYUUAutoSeedPlugin._build_download_url(1, "www.yemapt.org", "api/torrent/download?id={}", 77)
        assert url == "https://www.yemapt.org/api/torrent/download?id=77"

    def test_gazelle_strips_authkey_and_torrent_pass(self):
        url = IYUUAutoSeedPlugin._build_download_url(
            1, "dicmusic.com", "torrents.php?action=download&id={}&authkey={authkey}&torrent_pass={torrent_pass}", 5
        )
        assert url == "https://dicmusic.com/torrents.php?action=download&id=5"


class TestCanSeeding:
    def test_paused_completed_can_seed(self):
        assert IYUUAutoSeedPlugin._can_seeding(_torrent()) is True

    def test_uploading_completed_can_seed(self):
        assert IYUUAutoSeedPlugin._can_seeding(_torrent(status=TorrentStatus.Uploading)) is True

    def test_downloading_cannot_seed(self):
        assert IYUUAutoSeedPlugin._can_seeding(_torrent(status=TorrentStatus.Downloading)) is False

    def test_incomplete_cannot_seed(self):
        assert IYUUAutoSeedPlugin._can_seeding(_torrent(progress=99)) is False


class TestDownloadTorrent:
    def _seed(self, **overrides):
        seed = {"sid": 1, "torrent_id": 12345, "info_hash": "deadbeef"}
        seed.update(overrides)
        return seed

    def _setup_success_path(self, plugin):
        _mock_helper(plugin).get_torrent_url.return_value = (
            "pt.example.com",
            "download.php?id={}&passkey={passkey}",
            2,
        )
        plugin._sites.get_sites.return_value = {
            "id": 10,
            "cookie": "uid=1",
            "ua": "UA",
            "proxy": False,
        }
        plugin._downloader.get_torrents.return_value = []
        client = MagicMock()
        client.add_torrent.return_value = True
        plugin._downloader.get_downloader.return_value = client
        return client

    def test_success_adds_via_client(
        self,
    ):
        plugin = _make_plugin()
        client = self._setup_success_path(plugin)
        with patch(f"{MODULE}.HttpClient") as mock_http:
            mock_http.return_value.get.return_value = MagicMock(content=b"torrent-bytes")
            result = plugin._download_torrent(self._seed(), "d1", "/downloads", [])
        assert result is True
        assert plugin.success == 1
        # 验证下载链接拼接正确
        req_url = mock_http.return_value.get.call_args.args[0]
        assert req_url == "https://pt.example.com/download.php?id=12345"
        # 验证通过客户端实例添加
        client.add_torrent.assert_called_once_with(
            content=b"torrent-bytes",
            is_paused=True,
            download_dir="/downloads",
            tag=["已整理", "辅种"],
        )
        assert plugin._recheck_torrents["d1"] == ["deadbeef"]

    def test_existing_hash_skipped(self):
        plugin = _make_plugin()
        self._setup_success_path(plugin)
        plugin._downloader.get_torrents.return_value = [_torrent()]
        result = plugin._download_torrent(self._seed(), "d1", "/downloads", [])
        assert result is False
        assert plugin.exist == 1
        plugin._downloader.get_downloader.assert_not_called()

    def test_gendltoken_site_skipped(self):
        plugin = _make_plugin()
        _mock_helper(plugin).get_torrent_url.return_value = ("api.m-team.cc", "api/torrent/genDlToken", 2)
        plugin._sites.get_sites.return_value = {"id": 1}
        result = plugin._download_torrent(self._seed(), "d1", "/downloads", [])
        assert result is False
        assert plugin.fail == 1

    def test_path_placeholder_fails(self):
        plugin = _make_plugin()
        _mock_helper(plugin).get_torrent_url.return_value = ("totheglory.im", "dl/{}/{passkey}", 2)
        plugin._sites.get_sites.return_value = {"id": 1, "cookie": "c", "ua": "UA", "proxy": False}
        plugin._downloader.get_torrents.return_value = []
        result = plugin._download_torrent(self._seed(), "d1", "/downloads", [])
        assert result is False
        assert plugin.fail == 1
        plugin._downloader.get_downloader.assert_not_called()

    def test_sites_cfg_filter(self):
        plugin = _make_plugin()
        _mock_helper(plugin).get_torrent_url.return_value = (
            "pt.example.com",
            "download.php?id={}",
            2,
        )
        plugin._sites.get_sites.return_value = {"id": 10}
        result = plugin._download_torrent(self._seed(), "d1", "/downloads", ["99"])
        assert result is False
        assert plugin.realtotal == 0

    def test_add_torrent_failure(self):
        plugin = _make_plugin()
        client = self._setup_success_path(plugin)
        client.add_torrent.return_value = False
        with patch(f"{MODULE}.HttpClient") as mock_http:
            mock_http.return_value.get.return_value = MagicMock(content=b"torrent-bytes")
            result = plugin._download_torrent(self._seed(), "d1", "/downloads", [])
        assert result is False
        assert plugin.fail == 1
        assert "d1" not in plugin._recheck_torrents


class TestIyuuHelperGetTorrentUrl:
    def test_returns_three_tuple(self):
        helper = IyuuHelper(token="t")
        helper._sites = {1: {"base_url": "pt.example.com", "download_page": "download.php?id={}", "is_https": 2}}
        assert helper.get_torrent_url(1) == ("pt.example.com", "download.php?id={}", 2)

    def test_unknown_sid(self):
        helper = IyuuHelper(token="t")
        # _sites 为空会触发联网拉取，使用非空字典避免真实请求
        helper._sites = {1: {"base_url": "a.com", "download_page": "dl?id={}", "is_https": 2}}
        assert helper.get_torrent_url(99) == (None, None, None)

    def test_empty_sid(self):
        helper = IyuuHelper(token="t")
        assert helper.get_torrent_url(None) == (None, None, None)


class TestPluginApiHandlers:
    def _make_api_plugin(self, token="tok"):
        plugin = _make_plugin()
        _mock_ctx(plugin).get_config.return_value = {"token": token, "rate_limit": "5/s"}
        _mock_helper(plugin).get_torrent_url.return_value = (None, None, None)
        plugin._sites.get_sites.return_value = {}
        plugin._sites.get_sites_by_name.return_value = []
        return plugin

    def test_bindable_sites(self):
        plugin = self._make_api_plugin()
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.get_auth_sites.return_value = (
                [{"id": 2, "site": "pthome", "nickname": "铂金家"}],
                "",
            )
            result = plugin._api_bindable_sites({})
        assert result["success"] is True
        assert result["data"] == [{"id": 2, "site": "pthome", "nickname": "铂金家"}]
        mock_helper_cls.assert_called_once_with(token="tok", site_engine=plugin.ctx.site_engine, rate_limit="5/s")

    def test_bindable_sites_enriches_api_key_by_url(self):
        plugin = self._make_api_plugin()
        _mock_helper(plugin).get_torrent_url.return_value = ("pthome.net", "download.php?id={}", 1)
        plugin._sites.get_sites.return_value = {"id": 5, "api_key": "local-key"}
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.get_auth_sites.return_value = (
                [{"id": 2, "site": "pthome", "nickname": "铂金家"}],
                "",
            )
            result = plugin._api_bindable_sites({})
        row = result["data"][0]
        assert row["local"] is True
        assert row["api_key"] == "local-key"

    def test_bindable_sites_fallback_by_nickname(self):
        """URL 不匹配时（如 m-team）按站点定义名称回退解析"""
        plugin = self._make_api_plugin()
        _mock_helper(plugin).get_torrent_url.return_value = ("api.m-team.cc", "api/torrent/genDlToken", 2)
        plugin._sites.get_sites.side_effect = [
            {},
            {"id": 3, "api_key": "mteam-key"},
        ]
        site_def = MagicMock()
        site_def.api.base_url = "https://api.m-team.io"
        plugin.ctx.site_engine.get_by_name.return_value = site_def
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.get_auth_sites.return_value = (
                [{"id": 3, "site": "m-team", "nickname": "馒头"}],
                "",
            )
            result = plugin._api_bindable_sites({})
        row = result["data"][0]
        assert row["local"] is True
        assert row["api_key"] == "mteam-key"
        plugin.ctx.site_engine.get_by_name.assert_called_once_with("馒头")

    def test_bindable_sites_without_token(self):
        plugin = self._make_api_plugin(token="")
        result = plugin._api_bindable_sites({})
        assert result == {"success": False, "message": "未配置 IYUU Token"}

    def test_bind_site_success(self):
        plugin = self._make_api_plugin()
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.bind_site.return_value = ({"ok": 1}, "")
            result = plugin._api_bind_site({"site": "pthome", "passkey": "pk", "uid": "100"})
        assert result["success"] is True
        mock_helper_cls.return_value.bind_site.assert_called_once_with("pthome", "pk", "100")

    def test_bind_site_missing_params(self):
        plugin = self._make_api_plugin()
        result = plugin._api_bind_site({"site": "pthome", "passkey": "", "uid": "100"})
        assert result["success"] is False
        assert "不能为空" in result["message"]

    def test_bind_site_iyuu_error(self):
        plugin = self._make_api_plugin()
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.bind_site.return_value = (None, "获取站点id失败")
            result = plugin._api_bind_site({"site": "unknown", "passkey": "pk", "uid": "1"})
        assert result == {"success": False, "message": "获取站点id失败"}

    def test_bindable_sites_iyuu_error_propagates(self):
        """IYUU 接口报错（如限流）应透传而不是吞掉"""
        plugin = self._make_api_plugin()
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.get_auth_sites.return_value = (
                [],
                "请求IYUU失败，状态码：400，返回信息：访问频率过快",
            )
            result = plugin._api_bindable_sites({})
        assert result["success"] is False
        assert "访问频率过快" in result["message"]

    def test_bind_site_persists_record(self):
        """绑定成功后落盘 bound_sites.json，列表接口回显已绑定状态"""
        plugin = self._make_api_plugin()
        store = {}

        def fake_read(filename):
            return store.get(filename)

        def fake_write(filename, content):
            store[filename] = content

        _mock_ctx(plugin).read_data.side_effect = fake_read
        _mock_ctx(plugin).write_data.side_effect = fake_write
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.bind_site.return_value = ({"ok": 1}, "")
            result = plugin._api_bind_site({"site": "pthome", "passkey": "pk", "uid": "100"})
        assert result["success"] is True
        saved = store.get("bound_sites.json")
        assert saved is not None
        import json as _json

        record = _json.loads(saved)
        assert record["pthome"]["uid"] == "100"
        assert record["pthome"]["time"]

        # 列表接口回显已绑定状态
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.get_auth_sites.return_value = (
                [{"id": 2, "site": "pthome", "nickname": "铂金家"}],
                "",
            )
            list_result = plugin._api_bindable_sites({})
        row = list_result["data"][0]
        assert row["bound"] is True
        assert row["bound_uid"] == "100"

    def test_bind_site_failure_not_persisted(self):
        plugin = self._make_api_plugin()
        _mock_ctx(plugin).read_data.return_value = None
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.bind_site.return_value = (None, "绑定失败")
            result = plugin._api_bind_site({"site": "pthome", "passkey": "pk", "uid": "100"})
        assert result["success"] is False
        _mock_ctx(plugin).write_data.assert_not_called()

    def test_bindable_sites_html_def_fallback(self):
        """HTML 站点定义（无 api）按名称匹配本地配置"""
        plugin = self._make_api_plugin()
        _mock_helper(plugin).get_torrent_url.return_value = ("www.hdkyl.in", "download.php?id={}&passkey={passkey}", 1)
        plugin._sites.get_sites.return_value = {}
        plugin._sites.get_sites_by_name.return_value = [
            {"id": 70, "name": "麒麟", "api_key": ""},
        ]
        site_def = MagicMock()
        site_def.name = "麒麟"
        site_def.api = None
        plugin.ctx.site_engine.get_by_name.return_value = site_def
        with patch(f"{MODULE}.IyuuHelper") as mock_helper_cls:
            mock_helper_cls.return_value.get_auth_sites.return_value = (
                [{"id": 97, "site": "hdkyl", "nickname": "麒麟"}],
                "",
            )
            result = plugin._api_bindable_sites({})
        row = result["data"][0]
        assert row["local"] is True
