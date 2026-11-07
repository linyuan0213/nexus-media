"""Tests for app.sites.torrent."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import site_priority_order
from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo
from app.sites.torrent import Torrent


def test_site_priority_order_supports_values_above_100():
    assert site_priority_order(1) > site_priority_order(100) > site_priority_order(101)
    assert site_priority_order(9999) == 0
    assert site_priority_order(10000) == 0


class _MediaInfo(MediaInfo):
    def __init__(self, **kwargs):
        super().__init__()
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestTorrentGetDownloadList:
    """Test suite for Torrent.get_download_list."""

    def test_prioritizes_season_pack_over_single_episodes(self):
        single = _MediaInfo(
            title="Single Ep",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=1,
            seeders=100,
        )
        pack = _MediaInfo(
            title="Season Pack",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            res_order=1,
            site_order=1,
            seeders=10,
        )
        result = Torrent.get_download_list([single, pack], download_order="default")
        assert result[0].title == "Season Pack"

    def test_prioritizes_multi_episode_pack(self):
        single = _MediaInfo(
            title="Single Ep",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=1,
            seeders=100,
        )
        multi = _MediaInfo(
            title="E01-E12 Pack",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=12,
            res_order=1,
            site_order=1,
            seeders=50,
        )
        result = Torrent.get_download_list([single, multi], download_order="default")
        assert result[0].title == "E01-E12 Pack"

    def test_site_mode_prefers_lower_pri_site(self):
        """site_order=100-pri（pri 越小=主站越优先）：site 模式应选 pri 小（site_order 大）的站点"""
        low = _MediaInfo(
            title="Low",
            type=ProviderMediaType.MOVIE,
            res_order=0,
            site_order=9999,
            seeders=5,
        )
        high = _MediaInfo(
            title="High",
            type=ProviderMediaType.MOVIE,
            res_order=0,
            site_order=0,
            seeders=500,
        )
        result = Torrent.get_download_list([low, high], download_order="site")
        assert result[0].title == "Low"

    def test_site_mode_site_priority_beats_rule_order(self):
        high_site = _MediaInfo(
            title="HighSite",
            type=ProviderMediaType.MOVIE,
            res_order=0,
            site_order=9999,
            seeders=1,
        )
        high_rule = _MediaInfo(
            title="HighRule",
            type=ProviderMediaType.MOVIE,
            res_order=99,
            site_order=0,
            seeders=999,
        )
        result = Torrent.get_download_list([high_rule, high_site], download_order="site")
        assert result[0].title == "HighSite"

    def test_site_mode_same_site_prefers_higher_rule(self):
        """site 模式：同一站点内规则顺序第二，优先于做种数."""
        same_site_low_seed = _MediaInfo(
            title="LowSeedHighRule",
            type=ProviderMediaType.MOVIE,
            res_order=99,
            site_order=9999,
            seeders=5,
        )
        same_site_high_seed = _MediaInfo(
            title="HighSeedLowRule",
            type=ProviderMediaType.MOVIE,
            res_order=1,
            site_order=9999,
            seeders=500,
        )
        result = Torrent.get_download_list([same_site_low_seed, same_site_high_seed], download_order="site")
        assert result[0].title == "LowSeedHighRule"

    def test_seeder_mode_prefers_more_seeders_over_site_priority(self):
        """做种数优先：低优先级站点做种更多时应胜出."""
        preferred_site = _MediaInfo(
            title="PreferredSite",
            type=ProviderMediaType.MOVIE,
            res_order=1,
            site_order=9999,
            seeders=5,
        )
        other_site = _MediaInfo(
            title="OtherSite",
            type=ProviderMediaType.MOVIE,
            res_order=99,
            site_order=0,
            seeders=500,
        )
        result = Torrent.get_download_list([preferred_site, other_site], download_order="seeder")
        assert result[0].title == "OtherSite"

    def test_seeder_mode_tie_prefers_lower_pri_site(self):
        """seeder 模式种子数相同时，主站（pri 小、site_order 大）胜出"""
        low = _MediaInfo(
            title="Low",
            type=ProviderMediaType.MOVIE,
            res_order=0,
            site_order=9999,
            seeders=5,
        )
        high = _MediaInfo(
            title="High",
            type=ProviderMediaType.MOVIE,
            res_order=0,
            site_order=0,
            seeders=5,
        )
        result = Torrent.get_download_list([low, high], download_order="seeder")
        assert result[0].title == "Low"

    def test_collapse_keeps_single_best_candidate_per_name(self):
        first = _MediaInfo(
            title="Same Show",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=9999,
            seeders=10,
        )
        second = _MediaInfo(
            title="Same Show",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=0,
            seeders=10,
        )
        result = Torrent.get_download_list([first, second], download_order="site")
        assert len(result) == 1
        assert result[0] is first

    def test_no_collapse_keeps_multi_site_candidates_in_order(self):
        first = _MediaInfo(
            title="Same Show",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=9999,
            seeders=10,
        )
        second = _MediaInfo(
            title="Same Show",
            type=ProviderMediaType.ANIME,
            tmdb_id=1,
            begin_season=1,
            begin_episode=1,
            end_episode=1,
            res_order=1,
            site_order=0,
            seeders=10,
        )
        result = Torrent.get_download_list([first, second], download_order="site", collapse=False)
        assert result == [first, second]


class TestTorrentContentErrors:
    def test_json_limit_marked_unretryable(self):
        content = '{"code":"1","message":"相同種子當天最多下載10次","data":null}'.encode()
        msg = Torrent._content_error_message(content)
        assert msg.startswith("[不可重试]站点返回：")
        assert "最多下載10次" in msg

    def test_json_without_message(self):
        msg = Torrent._content_error_message(b'{"code":"1"}')
        assert "[不可重试]" in msg and "JSON" in msg

    def test_html_response_message(self):
        msg = Torrent._content_error_message(b"<!DOCTYPE html><html>login</html>")
        assert "网页" in msg

    def test_garbage_response_message(self):
        msg = Torrent._content_error_message(b"something else")
        assert "失效" in msg

    def test_safe_decode_raises_on_truncated_without_crash(self):
        with pytest.raises(Exception):
            Torrent._safe_decode(b"d8:announce146:https://tracker.m-team.cc/announce?cred")

    def test_safe_decode_parses_valid_torrent(self):
        torrent = Torrent._safe_decode(b"d8:announce4:http4:infod6:lengthi1e4:name1:aee")
        assert torrent["announce"] == "http"

    def _torrent(self):
        engine = MagicMock()
        engine.get_by_url.return_value = None
        engine.site_limiter = None
        return Torrent(engine)

    def _response(self, content: bytes):
        resp = MagicMock()
        resp.content = content
        resp.text = content.decode("utf-8", errors="ignore")
        resp.headers = {"content-type": "application/json"}
        return resp

    def test_save_torrent_file_json_limit_returns_unretryable(self):
        torrent = self._torrent()
        resp = self._response('{"code":"1","message":"相同種子當天最多下載10次"}'.encode())
        with patch("app.sites.torrent.HttpClient") as client:
            client.return_value.get.return_value = resp
            path, content, msg = torrent.save_torrent_file("https://api.m-team.cc/api/rss/dlv2?sign=abc&t=1")
        assert path is None and content is None
        assert "不可重试" in msg and "最多下載10次" in msg

    def _redirect(self, status_code: int, location: str):
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {"location": location}
        resp.content = b""
        resp.text = ""
        return resp

    def test_prowlarr_magnet_redirect_returns_magnet(self):
        """Prowlarr/Jackett 下载接口 302 到 magnet: 时应直接返回磁力链接

        回归：此前 HttpClient 自动跟随跳转 → httpx 报
        "Request URL has an unsupported protocol 'magnet://'" → 下载失败。
        """
        torrent = self._torrent()
        magnet = "magnet:?xt=urn:btih:ABCDEF123456&dn=Show"
        with patch("app.sites.torrent.HttpClient") as client:
            client.return_value.get.return_value = self._redirect(302, magnet)
            path, content, msg = torrent.save_torrent_file("http://192.168.1.1:9696/6/download?apikey=k&link=a1lv")
        assert path is None
        assert content == magnet
        assert msg == "磁力链接"
        assert client.return_value.get.call_args.kwargs["follow_redirects"] is False

    def test_http_redirect_followed_manually(self):
        """302 指向 http(s) 种子地址时手动跟一跳，仍走原有解析逻辑"""
        torrent = self._torrent()
        magnet = "magnet:?xt=urn:btih:ZZZ"
        first = self._redirect(302, "https://cdn.example.com/a.torrent")
        second = MagicMock()
        second.status_code = 200
        second.content = magnet.encode()
        second.text = magnet
        second.headers = {"content-type": "application/x-bittorrent"}
        with patch("app.sites.torrent.HttpClient") as client:
            client.return_value.get.side_effect = [first, second]
            path, content, msg = torrent.save_torrent_file("https://site.example.com/dl/1")
        assert content == magnet
        assert client.return_value.get.call_count == 2
        assert client.return_value.get.call_args_list[1].kwargs["url"] == "https://cdn.example.com/a.torrent"


class TestIntersectionEpisodes:
    def test_explicit_empty_target_stays_empty(self):
        """缺集已清空时不能被媒体库缺失集重新填满（避免重复下载）."""
        target = {"id1": [{"season": 1, "episodes": [], "total_episodes": 12}]}
        source = {"id1": [{"season": 1, "episodes": [1, 2], "total_episodes": 12}]}

        result = Torrent.get_intersection_episodes(target, source, "id1")

        assert result["id1"][0]["episodes"] == []

    def test_unknown_target_still_inherits_source(self):
        """目标没有 episodes 字段时才继承媒体库缺失集."""
        target = {"id1": [{"season": 1, "total_episodes": 12}]}
        source = {"id1": [{"season": 1, "episodes": [1, 2], "total_episodes": 12}]}

        result = Torrent.get_intersection_episodes(target, source, "id1")

        assert result["id1"][0]["episodes"] == [1, 2]

    def test_non_empty_target_intersects(self):
        target = {"id1": [{"season": 1, "episodes": [1, 2, 3]}]}
        source = {"id1": [{"season": 1, "episodes": [2, 3, 4]}]}

        result = Torrent.get_intersection_episodes(target, source, "id1")

        assert set(result["id1"][0]["episodes"]) == {2, 3}
