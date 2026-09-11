"""DownloadCore batch_download 完整流程测试"""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.services.download_core import DownloadCore


class MockMediaItem:
    """Mock 媒体信息对象"""

    def __init__(self, **kwargs):
        self.type = kwargs.get("type", MediaType.TV)
        self.title = kwargs.get("title", "Test")
        self.tmdb_id = kwargs.get("tmdb_id", 123)
        self.enclosure = kwargs.get("enclosure", "")
        self.page_url = kwargs.get("page_url", "")
        self.org_string = kwargs.get("org_string", "")
        self._season_list = kwargs.get("season_list", [1])
        self._episode_list = kwargs.get("episode_list", [])
        self.downloader_id = None
        self.download_id = None
        self.save_path = None
        self.download_setting = None
        self.size = 0
        self.category = ""
        self.res_order = kwargs.get("res_order", 100)
        self.site_order = kwargs.get("site_order", 100)
        self.seeders = kwargs.get("seeders", 0)
        self.user_id = kwargs.get("user_id", None)

    def get_season_list(self):
        return self._season_list

    def get_episode_list(self):
        return self._episode_list

    def get_title_string(self):
        return self.title

    def get_season_episode_string(self):
        season = self._season_list[0] if self._season_list else 1
        if self._episode_list:
            eps = ",".join(str(e) for e in self._episode_list)
            return f"S{season:02d}E{eps}"
        return f"S{season:02d}"

    def to_dict(self):
        return {"title": self.title, "type": self.type.value}


class TestBatchDownloadFlow:
    @pytest.fixture
    def mock_core(self):
        mock_factory = MagicMock()
        mock_factory.download_order = None
        mock_factory.default_downloader_id = "thunder-1"

        with patch("app.services.download_core.DownloadPipeline") as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_pipeline_cls.return_value = mock_pipeline

            core = DownloadCore(
                client_factory=mock_factory,
                message=MagicMock(),
                mediaserver=MagicMock(),
                filetransfer=MagicMock(),
                sites=MagicMock(),
                siteconf=MagicMock(),
                sitesubtitle=MagicMock(),
                event_bus=MagicMock(),
                download_repo=MagicMock(),
                download_setting_repo=MagicMock(),
                systemconfig=MagicMock(),
                downloader_repo=MagicMock(),
                site_engine=MagicMock(),
            )
            core._pipeline = mock_pipeline
            yield core, mock_pipeline

    def test_batch_download_movie_only(self, mock_core):
        core, pipeline = mock_core
        movie = MockMediaItem(type=MediaType.MOVIE, enclosure="url1")

        def mock_download(**kwargs):
            return "thunder-1", "tid1", ""

        core.download = mock_download

        downloaded, left = core.batch_download("WEB", [movie])
        assert len(downloaded) == 1
        assert movie in downloaded
        assert len(left) == 0

    def test_batch_download_tv_with_need_tvs(self, mock_core):
        core, pipeline = mock_core
        movie = MockMediaItem(type=MediaType.MOVIE, enclosure="movie-url", title="Movie")
        tv_item = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=123,
            season_list=[1],
            episode_list=[1, 2],
            enclosure="tv-url",
            title="TV Show",
        )

        call_count = 0

        def mock_download(**kwargs):
            nonlocal call_count
            call_count += 1
            return "thunder-1", f"tid{call_count}", ""

        core.download = mock_download

        need_tvs = {123: [{"season": 1, "episodes": [1, 2, 3], "total_episodes": 12}]}
        downloaded, left = core.batch_download("WEB", [movie, tv_item], need_tvs=need_tvs)

        assert len(downloaded) == 2
        assert movie in downloaded
        assert tv_item in downloaded
        assert need_tvs[123][0]["episodes"] == [3]

    def test_batch_download_season_pack_unpack(self, mock_core):
        core, pipeline = mock_core
        season_pack = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=456,
            season_list=[1],
            episode_list=[],
            enclosure="pack-url",
            org_string="Show S01 Pack",
        )

        def mock_download(**kwargs):
            return "thunder-1", "tid-pack", ""

        def mock_torrent_episodes(url, page_url=None):
            return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "path"

        core.download = mock_download
        core.get_torrent_episodes = mock_torrent_episodes

        need_tvs = {456: [{"season": 1, "episodes": [], "total_episodes": 12}]}
        downloaded, left = core.batch_download("RSS", [season_pack], need_tvs=need_tvs)

        assert len(downloaded) == 1
        assert season_pack in downloaded
        assert 456 not in need_tvs

    def test_batch_download_unpack_from_season_pack(self, mock_core):
        core, pipeline = mock_core
        season_pack = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=789,
            season_list=[1],
            episode_list=[],
            enclosure="pack-url",
            org_string="Show S01 Pack",
        )

        def mock_download(**kwargs):
            return "thunder-1", "tid-unpack", ""

        def mock_torrent_episodes(url, page_url=None):
            return [3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "path"

        files_status_calls = []

        def mock_set_files(tid, need_episodes, downloader_id=None):
            files_status_calls.append((tid, need_episodes))
            return []

        start_calls = []

        def mock_start(ids, downloader_id=None):
            start_calls.append(ids)

        core.download = mock_download
        core.get_torrent_episodes = mock_torrent_episodes
        core.set_files_status = mock_set_files
        core.start_torrents = mock_start

        need_tvs = {789: [{"season": 1, "episodes": [4, 5], "total_episodes": 12}]}
        downloaded, left = core.batch_download("RSS", [season_pack], need_tvs=need_tvs)

        assert len(downloaded) == 1
        assert season_pack in downloaded
        assert 789 not in need_tvs
        assert files_status_calls == [("tid-unpack", [4, 5])]
        assert start_calls == ["tid-unpack"]

    def test_batch_download_all_episodes_already_have(self, mock_core):
        core, pipeline = mock_core
        tv_item = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=999,
            season_list=[1],
            episode_list=[1, 2, 3],
            enclosure="tv-url",
        )

        def mock_download(**kwargs):
            return "thunder-1", "tid1", ""

        core.download = mock_download

        need_tvs = {999: [{"season": 1, "episodes": [1, 2, 3], "total_episodes": 12}]}
        downloaded, left = core.batch_download("WEB", [tv_item], need_tvs=need_tvs)

        assert len(downloaded) == 1
        # 全部集下载完成后 need_tvs 中该条目会被移除
        assert 999 not in need_tvs

    def test_batch_download_left_medias(self, mock_core):
        core, pipeline = mock_core
        movie = MockMediaItem(type=MediaType.MOVIE, enclosure="url1", title="Movie")
        tv_item = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=111,
            season_list=[1],
            episode_list=[5, 6],
            enclosure="tv-url",
            title="TV Show",
        )

        def mock_download(**kwargs):
            if kwargs["media_info"].type == MediaType.MOVIE:
                return "thunder-1", "tid1", ""
            return "thunder-1", None, "fail"

        core.download = mock_download

        need_tvs = {111: [{"season": 1, "episodes": [5, 6], "total_episodes": 12}]}
        downloaded, left = core.batch_download("WEB", [movie, tv_item], need_tvs=need_tvs)

        assert len(downloaded) == 1
        assert movie in downloaded
        assert len(left) == 1
        assert tv_item in left

    def test_batch_download_empty_list(self, mock_core):
        core, pipeline = mock_core
        downloaded, left = core.batch_download("WEB", [], need_tvs={})
        assert len(downloaded) == 0
        assert len(left) == 0

    def test_batch_download_with_download_order(self, mock_core):
        core, pipeline = mock_core
        core._client_factory.download_order = "seeder"

        movie1 = MockMediaItem(type=MediaType.MOVIE, enclosure="url1", title="A")
        movie2 = MockMediaItem(type=MediaType.MOVIE, enclosure="url2", title="B")

        def mock_download(**kwargs):
            return "thunder-1", "tid1", ""

        core.download = mock_download

        downloaded, left = core.batch_download("WEB", [movie1, movie2])
        assert len(downloaded) == 2


class TestDownloadShortCircuitAndCache:
    """同轮去重：失败短路与种子解析缓存."""

    @pytest.fixture
    def mock_core(self):
        mock_factory = MagicMock()
        mock_factory.download_order = None

        with patch("app.services.download_core.DownloadPipeline") as mock_pipeline_cls:
            mock_pipeline_cls.return_value = MagicMock()
            core = DownloadCore(
                client_factory=mock_factory,
                message=MagicMock(),
                mediaserver=MagicMock(),
                filetransfer=MagicMock(),
                sites=MagicMock(),
                siteconf=MagicMock(),
                sitesubtitle=MagicMock(),
                event_bus=MagicMock(),
                download_repo=MagicMock(),
                download_setting_repo=MagicMock(),
                systemconfig=MagicMock(),
                downloader_repo=MagicMock(),
                site_engine=MagicMock(),
            )
            core._episode_cache.clear()
            core._download_fail_cache.clear()
            yield core

    def test_download_failure_short_circuits_same_enclosure(self, mock_core):
        core = mock_core
        core._pipeline.execute.return_value = (None, None, "[不可重试]站点返回：相同種子當天最多下載10次")
        media = MockMediaItem(enclosure="http://site/dlv2?sign=abc", page_url="http://site/detail/1")

        first = core.download(media)
        second = core.download(media)

        assert first[1] is None and second[1] is None
        assert core._pipeline.execute.call_count == 1
        assert "不可重试" in second[2]

    def test_download_success_is_not_short_circuited(self, mock_core):
        core = mock_core
        core._pipeline.execute.return_value = ("qb", "tid1", "")
        media = MockMediaItem(enclosure="http://site/dlv2?sign=ok")

        assert core.download(media)[1] == "tid1"
        assert core.download(media)[1] == "tid1"
        assert core._pipeline.execute.call_count == 2

    def test_get_torrent_episodes_caches_within_round(self, mock_core):
        core = mock_core
        with patch("app.services.download_core.Torrent") as torrent_cls:
            torrent_cls.return_value.get_torrent_info.return_value = (
                "/tmp/a.torrent",
                b"data",
                "",
                ["Show.S01E01.mkv", "Show.S01E02.mkv"],
                "",
            )
            with patch("app.services.download_core.meta_info") as meta:
                m1, m2 = MagicMock(), MagicMock()
                m1.begin_episode = 1
                m1.get_episode_list.return_value = [1]
                m2.begin_episode = 2
                m2.get_episode_list.return_value = [2]
                meta.side_effect = [m1, m2]

                first = core.get_torrent_episodes("http://site/dlv2?sign=x")
                second = core.get_torrent_episodes("http://site/dlv2?sign=x")

        assert first[0] == [1, 2]
        assert first[1] == "/tmp/a.torrent"
        assert second == ([1, 2], "/tmp/a.torrent")
        assert torrent_cls.return_value.get_torrent_info.call_count == 1

    def test_batch_download_resets_episode_cache(self, mock_core):
        core = mock_core
        core._episode_cache.set("stale", ([1], "/tmp/old"))
        core.batch_download("WEB", [])
        assert core._episode_cache.get("stale") is None

    def test_batch_download_uses_item_owner_user_id(self, mock_core):
        """多用户：候选自带 user_id 优先，缺失时回退批量层 user_id."""
        core = mock_core
        owned = MockMediaItem(type=MediaType.MOVIE, enclosure="a", title="A", tmdb_id=1)
        owned.user_id = 7
        fallback = MockMediaItem(type=MediaType.MOVIE, enclosure="b", title="B", tmdb_id=2)
        fallback.user_id = None
        seen: dict[str, object] = {}

        def mock_download(**kwargs):
            seen[kwargs["media_info"].enclosure] = kwargs.get("user_id")
            return "qb", "tid", ""

        core.download = mock_download
        core.batch_download("WEB", [owned, fallback], user_id=3)

        assert seen["a"] == 7
        assert seen["b"] == 3

    def test_concurrent_same_link_single_flight(self, mock_core):
        core = mock_core
        calls = {"n": 0}

        def slow_execute(**kwargs):
            calls["n"] += 1
            time.sleep(0.2)
            return None, None, "[不可重试]站点返回：相同種子當天最多下載10次"

        core._pipeline.execute.side_effect = slow_execute
        media = MockMediaItem(enclosure="http://site/dlv2?sign=race")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: core.download(media), range(2)))

        assert calls["n"] == 1
        assert all(r[1] is None for r in results)

    def test_candidate_exception_does_not_break_batch(self, mock_core):
        """单个候选抛异常（如详情页抓取失败）不应中断整批，应回退下一个候选."""
        core = mock_core
        bad = MockMediaItem(type=MediaType.MOVIE, enclosure="a", title="A", tmdb_id=1)
        good = MockMediaItem(type=MediaType.MOVIE, enclosure="b", title="B", tmdb_id=2)

        def boom(**kwargs):
            if kwargs["media_info"].enclosure == "a":
                raise RuntimeError("种子详情页抓取为空")
            return "qb", "tid", ""

        core.download = boom
        downloaded, left = core.batch_download("WEB", [bad, good])
        assert downloaded == [good]
        assert bad in left

    def test_failed_candidate_falls_back_to_next(self, mock_core):
        core = mock_core
        first = MockMediaItem(type=MediaType.MOVIE, enclosure="url-bad", title="Bad")
        second = MockMediaItem(type=MediaType.MOVIE, enclosure="url-good", title="Good")

        def mock_download(**kwargs):
            if kwargs["media_info"].enclosure == "url-bad":
                return None, None, "[不可重试]站点返回：相同種子當天最多下載10次"
            return "thunder-1", "tid-ok", ""

        core.download = mock_download

        downloaded, left = core.batch_download("WEB", [first, second])
        assert downloaded == [second]
        assert first in left

    def test_failed_candidate_skipped_across_strategies(self, mock_core):
        core = mock_core
        bad = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=321,
            season_list=[1],
            episode_list=[],
            enclosure="pack-bad",
            org_string="Show S01 Pack",
        )
        good = MockMediaItem(
            type=MediaType.TV,
            tmdb_id=321,
            season_list=[1],
            episode_list=[],
            enclosure="pack-good",
            org_string="Show S01 Pack",
        )
        attempts = []

        def mock_download(**kwargs):
            attempts.append(kwargs["media_info"].enclosure)
            if kwargs["media_info"].enclosure == "pack-bad":
                return None, None, "[不可重试]限额"
            return "thunder-1", "tid-good", ""

        core.download = mock_download
        core.get_torrent_episodes = lambda url, page_url=None: ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "path")

        need_tvs = {321: [{"season": 1, "episodes": [], "total_episodes": 12}]}
        downloaded, left = core.batch_download("RSS", [bad, good], need_tvs=need_tvs)

        assert downloaded == [good]
        assert attempts == ["pack-bad", "pack-good"]


class TestGetDownloadDirInfo:
    """下载目录均衡选择测试."""

    def _media(self, mtype):
        media = MagicMock()
        media.type = mtype
        media.category = None
        media.size = 1024 * 1024 * 100
        return media

    def test_picks_first_when_single_match(self):
        from app.downloader.client_factory import DownloadClientFactory

        media = self._media(MediaType.MOVIE)
        dirs = [{"type": "movie", "save_path": "/data/tv/movies"}]
        info = DownloadClientFactory.get_download_dir_info(media, dirs)
        assert info["path"] == "/data/tv/movies"

    def test_picks_more_free_space_among_matches(self, monkeypatch):
        from app.downloader.client_factory import DownloadClientFactory

        media = self._media(MediaType.MOVIE)
        dirs = [
            {"type": "movie", "save_path": "/data/dir1"},
            {"type": "movie", "save_path": "/data/dir2"},
        ]
        monkeypatch.setattr("app.downloader.client_factory.os.path.exists", lambda p: True)
        monkeypatch.setattr(
            "app.downloader.client_factory.SystemUtils.get_free_space",
            lambda p: 1000 if "dir1" in p else 5000,
        )
        info = DownloadClientFactory.get_download_dir_info(media, dirs)
        assert info["path"] == "/data/dir2"

    def test_type_filter_respected(self):
        from app.downloader.client_factory import DownloadClientFactory

        media = self._media(MediaType.TV)
        dirs = [
            {"type": "movie", "save_path": "/data/movies"},
            {"type": "tv", "save_path": "/data/tv"},
        ]
        info = DownloadClientFactory.get_download_dir_info(media, dirs)
        assert info["path"] == "/data/tv"

    def test_too_small_free_space_skipped(self, monkeypatch):
        from app.downloader.client_factory import DownloadClientFactory

        media = self._media(MediaType.MOVIE)
        dirs = [
            {"type": "movie", "save_path": "/data/full"},
            {"type": "movie", "save_path": "/data/ok"},
        ]
        monkeypatch.setattr("app.downloader.client_factory.os.path.exists", lambda p: True)
        monkeypatch.setattr(
            "app.downloader.client_factory.SystemUtils.get_free_space",
            lambda p: 10 if "full" in p else 999999,
        )
        info = DownloadClientFactory.get_download_dir_info(media, dirs)
        assert info["path"] == "/data/ok"

    def test_empty_dir_returns_none(self):
        from app.downloader.client_factory import DownloadClientFactory

        media = self._media(MediaType.MOVIE)
        info = DownloadClientFactory.get_download_dir_info(media, [])
        assert info["path"] is None
