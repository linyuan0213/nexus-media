"""下载策略单元测试"""

from app.services.download_strategies import EpisodeStrategy, MovieDownloadStrategy, SeasonPackStrategy
from app.domain.mediatypes import MediaType


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

    def get_season_list(self):
        return self._season_list

    def get_episode_list(self):
        return self._episode_list


class TestMovieDownloadStrategy:
    def test_download_movies(self):
        movie1 = MockMediaItem(type=MediaType.MOVIE, enclosure="url1")
        movie2 = MockMediaItem(type=MediaType.MOVIE, enclosure="")
        tv = MockMediaItem(type=MediaType.TV)

        downloaded = []

        def download_cb(item, torrent_file=None, tag=None, is_paused=None):
            downloaded.append(item)
            return "did", "id1", ""

        def get_url_cb(page_url):
            return "resolved_url"

        result = MovieDownloadStrategy.download_movies([movie1, tv, movie2], download_cb, get_url_cb)
        assert len(result) == 2
        assert movie1 in result
        assert movie2 in result
        assert movie2.enclosure == "resolved_url"

    def test_download_movies_failure(self):
        movie = MockMediaItem(type=MediaType.MOVIE, enclosure="url1")

        def download_cb(item, torrent_file=None, tag=None, is_paused=None):
            return None, None, "error"

        result = MovieDownloadStrategy.download_movies([movie], download_cb, lambda x: x)
        assert len(result) == 0


class TestSeasonPackStrategy:
    def test_build_need_seasons(self):
        need_tvs = {
            123: [
                {"season": 1, "episodes": [], "total_episodes": 12},
                {"season": 2, "episodes": None, "total_episodes": 10},
            ]
        }
        result = SeasonPackStrategy.build_need_seasons(need_tvs)
        assert result == {123: [1, 2]}

    def test_build_need_seasons_empty(self):
        assert SeasonPackStrategy.build_need_seasons({}) == {}
        assert SeasonPackStrategy.build_need_seasons(None) == {}

    def test_find_season_packs_single_season(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[],
            enclosure="url1",
            org_string="Show S01 Pack",
        )

        def download_cb(item, torrent_file=None, tag=None, is_paused=None):
            return "did", "tid1", ""

        def get_ep_cb(url, page_url):
            return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "path"

        need_tvs = {123: [{"season": 1, "episodes": [], "total_episodes": 12}]}
        need_seasons = {123: [1]}

        result, updated_seasons, updated_need = SeasonPackStrategy.find_season_packs(
            [item], need_seasons, need_tvs, lambda x: x, download_cb, get_ep_cb
        )
        assert len(result) == 1
        assert 123 not in updated_seasons
        assert 123 not in updated_need

    def test_find_season_packs_insufficient_episodes(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[],
            enclosure="url1",
            org_string="Show S01 Pack",
        )

        def download_cb(item, torrent_file=None, tag=None, is_paused=None):
            return "did", "tid1", ""

        def get_ep_cb(url, page_url):
            return [1, 2, 3], "path"

        need_tvs = {123: [{"season": 1, "episodes": [], "total_episodes": 12}]}
        need_seasons = {123: [1]}

        result, updated_seasons, updated_need = SeasonPackStrategy.find_season_packs(
            [item], need_seasons, need_tvs, lambda x: x, download_cb, get_ep_cb
        )
        assert len(result) == 0
        assert 123 in updated_seasons

    def test_get_season_episodes(self):
        need_tvs = {123: [{"season": 1, "total_episodes": 12}]}
        assert SeasonPackStrategy._get_season_episodes(need_tvs, 123, 1) == 12
        assert SeasonPackStrategy._get_season_episodes(need_tvs, 123, 2) == 0
        assert SeasonPackStrategy._get_season_episodes({}, 123, 1) == 0


class TestEpisodeStrategy:
    def test_download_episodes_exact_match(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[3, 4],
            enclosure="url1",
        )

        def download_cb(item, torrent_file=None, tag=None, is_paused=None):
            return "did", "tid1", ""

        need_tvs = {123: [{"season": 1, "episodes": [1, 2, 3, 4, 5], "total_episodes": 12}]}

        result, updated = EpisodeStrategy.download_episodes(
            [item],
            need_tvs,
            lambda x: x,
            download_cb,
            lambda url, page: ([], None),
            lambda tid, eps, did: [],
            lambda ids, did: None,
            [],
        )
        assert len(result) == 1
        assert updated[123][0]["episodes"] == [1, 2, 5]

    def test_download_episodes_from_torrent(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[],
            enclosure="url1",
        )

        def download_cb(item, torrent_file=None, tag=None, is_paused=None):
            return "did", "tid1", ""

        def get_ep_cb(url, page_url):
            return [2, 3], "path"

        need_tvs = {123: [{"season": 1, "episodes": [1, 2, 3, 4], "total_episodes": 12}]}

        result, updated = EpisodeStrategy.download_episodes(
            [item],
            need_tvs,
            lambda x: x,
            download_cb,
            get_ep_cb,
            lambda tid, eps, did: [],
            lambda ids, did: None,
            [],
        )
        assert len(result) == 1
        assert updated[123][0]["episodes"] == [1, 4]

    def test_download_from_season_pack(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[],
            enclosure="url1",
            org_string="Show S01 1080p",
        )

        def download_cb(item, torrent_file=None, is_paused=None):
            return "did", "tid1", ""

        def get_ep_cb(url, page_url):
            return [1, 2, 3, 4, 5], "path"

        files_status_calls = []

        def set_files_cb(tid, need_episodes, downloader_id):
            files_status_calls.append((tid, need_episodes, downloader_id))
            return []

        start_calls = []

        def start_cb(ids, downloader_id):
            start_calls.append((ids, downloader_id))

        need_tvs = {123: [{"season": 1, "episodes": [2, 4], "total_episodes": 12}]}

        result, updated = EpisodeStrategy.download_from_season_pack(
            [item],
            need_tvs,
            lambda x: x,
            download_cb,
            get_ep_cb,
            set_files_cb,
            start_cb,
            [],
        )
        assert len(result) == 1
        assert 123 not in updated
        assert files_status_calls == [("tid1", [2, 4], "did")]
        assert start_calls == [("tid1", "did")]

    def test_download_from_season_pack_no_match(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[],
            enclosure="url1",
            org_string="Show S01 1080p",
        )

        def download_cb(item, torrent_file=None, is_paused=None):
            return "did", "tid1", ""

        def get_ep_cb(url, page_url):
            return [5, 6, 7], "path"

        need_tvs = {123: [{"season": 1, "episodes": [1, 2], "total_episodes": 12}]}

        result, updated = EpisodeStrategy.download_from_season_pack(
            [item],
            need_tvs,
            lambda x: x,
            download_cb,
            get_ep_cb,
            lambda tid, eps, did: [],
            lambda ids, did: None,
            [],
        )
        assert len(result) == 0
        assert updated[123][0]["episodes"] == [1, 2]

    def test_download_from_season_pack_no_need_episodes(self):
        item = MockMediaItem(
            tmdb_id=123,
            season_list=[1],
            episode_list=[],
            enclosure="url1",
        )

        need_tvs = {123: [{"season": 1, "episodes": None, "total_episodes": 12}]}

        result, updated = EpisodeStrategy.download_from_season_pack(
            [item],
            need_tvs,
            lambda x: x,
            lambda item, **kw: ("did", "tid1", ""),
            lambda url, page: ([1, 2], "path"),
            lambda tid, eps, did: [],
            lambda ids, did: None,
            [],
        )
        assert len(result) == 0
        assert 123 in updated

    def test_update_episodes(self):
        need_tvs = {123: [{"season": 1, "episodes": [1, 2, 3, 4, 5], "total_episodes": 12}]}
        result = EpisodeStrategy._update_episodes(need_tvs, 123, [1, 2, 3, 4, 5], [2, 4])
        assert result == [1, 3, 5]
        assert need_tvs[123][0]["episodes"] == [1, 3, 5]

    def test_update_episodes_all_downloaded(self):
        need_tvs = {123: [{"season": 1, "episodes": [1, 2], "total_episodes": 12}]}
        result = EpisodeStrategy._update_episodes(need_tvs, 123, [1, 2], [1, 2])
        assert result == []
        assert 123 not in need_tvs
