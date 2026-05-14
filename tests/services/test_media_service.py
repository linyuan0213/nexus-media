"""
MediaService 单元测试
"""

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.schemas.media import (
    LibrarySpaceDTO,
    MediaInfoResultDTO,
    MediaSearchResultDTO,
    SeasonEpisodesResultDTO,
    TransferHistoryPageDTO,
    UnknownListPageDTO,
)
from app.services.media_service import (
    MediaFileService,
    MediaInfoService,
    MediaLibraryService,
    MediaRecommendationService,
    SearchResultService,
    TransferHistoryService,
)
from app.utils.types import SystemConfigKey


class TestMediaInfoResultDTO:
    def test_default_values(self):
        dto = MediaInfoResultDTO()
        assert dto.type == ""
        assert dto.title == ""
        assert dto.seasons is None

    def test_with_values(self):
        dto = MediaInfoResultDTO(type="MOV", title="Test", seasons=[{"text": "第1季"}])
        assert dto.type == "MOV"
        assert dto.seasons == [{"text": "第1季"}]


class TestSeasonEpisodesResultDTO:
    def test_default(self):
        dto = SeasonEpisodesResultDTO()
        assert dto.episodes is None

    def test_with_episodes(self):
        dto = SeasonEpisodesResultDTO(episodes=[{"episode_number": 1}])
        assert dto.episodes is not None and len(dto.episodes) == 1


class TestSearchResultDTO:
    def test_default(self):
        dto = MediaSearchResultDTO()
        assert dto.total == 0
        assert dto.result is None


class TestTransferHistoryPageDTO:
    def test_default(self):
        dto = TransferHistoryPageDTO()
        assert dto.total == 0
        assert dto.page_num == 30
        assert dto.current_page == 1


class TestUnknownListPageDTO:
    def test_default(self):
        dto = UnknownListPageDTO()
        assert dto.total == 0
        assert dto.page_num == 30


class TestLibrarySpaceDTO:
    def test_default(self):
        dto = LibrarySpaceDTO()
        assert dto.used_percent == 0
        assert dto.free_space == ""


class TestMediaInfoService:
    @pytest.fixture
    def service(self):
        mock_media = MagicMock()
        mock_subscribe = MagicMock()
        mock_media_server = MagicMock()
        return MediaInfoService(media=mock_media, subscribe=mock_subscribe, media_server=mock_media_server)

    def test_get_season_episodes(self, service):
        service._media.get_tmdb_season_episodes.return_value = [{"episode_number": 1}, {"episode_number": 2}]
        service._media_server.check_item_exists.return_value = True
        result = service.get_season_episodes(tmdbid="123", title="Test", year="2024", season=1)
        assert len(result.episodes) == 2
        assert result.episodes[0]["state"] is True

    def test_get_tvseason_list_with_digit_tmdbid(self, service):
        service._media.get_tmdb_tv_seasons_byid.return_value = [{"season_number": 1}, {"season_number": 2}]
        result = service.get_tvseason_list(tmdbid="123", title=None)
        assert len(result) == 2
        assert result[0]["num"] == 1

    def test_get_tvseason_list_non_digit(self, service):
        with patch("app.services.media_service.WebUtils") as MockWeb:
            mock_media_info = MagicMock()
            mock_media_info.tmdb_info = {"id": 1}
            MockWeb.get_mediainfo_from_id.return_value = mock_media_info
            service._media.get_tmdb_tv_seasons.return_value = [{"season_number": 1}]
            result = service.get_tvseason_list(tmdbid="tv-123", title=None)
            assert len(result) == 1

    def test_get_tvseason_list_with_title_season(self, service):
        result = service.get_tvseason_list(tmdbid="123", title="Test S02")
        assert len(result) == 1
        assert result[0]["num"] == 2

    def test_get_media_info_detail_from_rss_movie(self, service):
        service._subscribe.get_subscribe_movies.return_value = {
            "1": {
                "overview": "desc",
                "poster": "img",
                "name": "Test",
                "vote": 8.5,
                "year": "2024",
                "release_date": "2024-01-01",
                "tmdbid": "123",
            }
        }
        service._media.get_detail_url.return_value = "http://tmdb/123"
        result = service.get_media_info_detail(mediaid=None, mtype="MOV", title="", year="", page=1, rssid="1")
        assert result.title == "Test"
        assert result.overview == "desc"

    def test_get_media_info_detail_fallback_to_tmdb(self, service):
        with patch("app.services.media_service.WebUtils") as MockWeb:
            mock_media = MagicMock()
            mock_media.tmdb_info = {"id": 123}
            mock_media.tmdb_id = "123"
            mock_media.get_detail_url.return_value = "http://tmdb/123"
            mock_media.overview = "overview"
            mock_media.get_poster_image.return_value = "img"
            mock_media.title = "Fallback"
            mock_media.vote_average = 7.5
            mock_media.year = "2024"
            MockWeb.get_mediainfo_from_id.return_value = mock_media
            service._media.get_media_info.return_value = mock_media
            service._subscribe.get_subscribe_id.return_value = None
            result = service.get_media_info_detail(mediaid="123", mtype="MOV", title="", year="", page=1, rssid=None)
            assert result.title == "Fallback"
            assert result.vote_average == 7.5

    def test_get_media_info_detail_no_tmdb_info(self, service):
        service._subscribe.get_subscribe_movies.return_value = {}
        with patch("app.services.media_service.WebUtils") as MockWeb:
            MockWeb.get_mediainfo_from_id.return_value = None
            service._media.get_media_info.return_value = None
            result = service.get_media_info_detail(
                mediaid=None, mtype="MOV", title="X", year="2024", page=1, rssid=None
            )
            assert result.title == "X"

    def test_get_media_person_by_tmdbid(self, service):
        service._media.get_tmdb_cats.return_value = [{"name": "Actor"}]
        result = service.get_media_person(tmdbid="123", mtype_str="MOV", keyword=None)
        assert result == [{"name": "Actor"}]

    def test_get_media_person_by_keyword(self, service):
        service._media.search_tmdb_person.return_value = [{"name": "Actor"}]
        result = service.get_media_person(tmdbid=None, mtype_str="MOV", keyword="John")
        assert result == [{"name": "Actor"}]

    def test_get_media_recommendations_movie(self, service):
        service._media.get_movie_recommendations.return_value = [{"title": "A"}]
        result = service.get_media_recommendations(tmdbid="123", mtype_str="MOV", page=1)
        assert result == [{"title": "A"}]

    def test_get_media_recommendations_tv(self, service):
        service._media.get_tv_recommendations.return_value = [{"title": "B"}]
        result = service.get_media_recommendations(tmdbid="123", mtype_str="TV", page=1)
        assert result == [{"title": "B"}]

    def test_get_media_similar_movie(self, service):
        service._media.get_movie_similar.return_value = [{"title": "C"}]
        result = service.get_media_similar(tmdbid="123", mtype_str="MOV", page=1)
        assert result == [{"title": "C"}]

    def test_get_person_medias_with_type(self, service):
        service._media.get_person_medias.return_value = [{"title": "D"}]
        result = service.get_person_medias(personid="1", mtype_str="MOV", page=1)
        assert result == [{"title": "D"}]

    def test_get_person_medias_no_type(self, service):
        service._media.get_person_medias.return_value = [{"title": "E"}]
        result = service.get_person_medias(personid="1", mtype_str=None, page=1)
        assert result == [{"title": "E"}]

    def test_name_test_unrecognized(self, service):
        service._media.get_media_info.return_value = None
        result = service.name_test(name="abc", subtitle=None)
        assert result["name"] == "无法识别"

    def test_name_test_recognized(self, service):
        mock_media = MagicMock()
        mock_media.title = "Test"
        service._media.get_media_info.return_value = mock_media
        with patch("app.utils.web_utils.mediainfo_dict") as mock_dict:
            mock_dict.return_value = {"name": "Test"}
            result = service.name_test(name="Test", subtitle=None)
            assert result["name"] == "Test"

    def test_search_media_infos(self, service):
        with patch("app.services.media_service.WebUtils") as MockWeb:
            mock_item = MagicMock()
            mock_item.to_dict.return_value = {"id": 1}
            MockWeb.search_media_infos.return_value = [mock_item]
            result = service.search_media_infos(keyword="test", source="tmdb", page=1)
            assert result == [{"id": 1}]

    def test_get_movie_calendar_douban(self, service):
        with patch("app.services.media_service.DouBan") as MockDouban:
            MockDouban().get_douban_detail.return_value = {
                "cover_url": "img",
                "title": "Test",
                "rating": {"value": 8.0},
                "pubdate": ["2024-01-01 (China)"],
            }
            result = service.get_movie_calendar(tid="DB:123", rssid="1")
            assert result["type"] == "电影"
            assert result["year"] == "2024"

    def test_get_movie_calendar_douban_no_date(self, service):
        with patch("app.services.media_service.DouBan") as MockDouban:
            MockDouban().get_douban_detail.return_value = {
                "cover_url": "",
                "title": "Test",
                "rating": {},
                "pubdate": [],
            }
            result = service.get_movie_calendar(tid="DB:123", rssid="1")
            assert result is None

    def test_get_movie_calendar_tmdb(self, service):
        service._media.get_tmdb_info.return_value = {
            "poster_path": "/img.jpg",
            "title": "Test",
            "vote_average": 8.0,
            "release_date": "2024-01-01",
        }
        with patch("app.services.media_service.Config") as MockCfg:
            MockCfg().get_tmdbimage_url.return_value = "http://img"
            result = service.get_movie_calendar(tid="123", rssid="1")
            assert result["title"] == "Test"
            assert result["year"] == "2024"

    def test_get_movie_calendar_no_tid(self, service):
        result = service.get_movie_calendar(tid=None, rssid="1")
        assert result is None

    def test_get_tv_calendar_douban(self, service):
        with patch("app.services.media_service.DouBan") as MockDouban:
            MockDouban().get_douban_detail.return_value = {
                "cover_url": "img",
                "title": "Test",
                "rating": {"value": 8.0},
                "pubdate": ["2024-01-01 (China)"],
            }
            result = service.get_tv_calendar(tid="DB:123", season=1, name="Test", rssid="1")
            assert len(result) == 1
            assert result[0]["type"] == "电视剧"

    def test_get_tv_calendar_tmdb(self, service):
        service._media.get_tmdb_tv_season_detail.return_value = {
            "air_date": "2024-01-01",
            "poster_path": "/poster.jpg",
            "episodes": [{"episode_number": 1, "air_date": "2024-01-01", "vote_average": 8.0}],
        }
        with patch("app.services.media_service.Config") as MockCfg:
            MockCfg().get_tmdbimage_url.return_value = "http://img"
            result = service.get_tv_calendar(tid="123", season=1, name="Test", rssid="1")
            assert len(result) == 1
            assert result[0]["type"] == "剧集"

    def test_get_media_detail(self, service):
        with (
            patch("app.services.media_service.WebUtils") as MockWeb,
            patch.object(service, "_get_media_exists_info") as mock_exists,
            patch("app.services.media_service.Config") as MockCfg,
        ):
            mock_media = MagicMock()
            mock_media.tmdb_info = {"id": 123}
            mock_media.tmdb_id = "123"
            mock_media.douban_id = ""
            mock_media.title = "Test"
            mock_media.year = "2024"
            mock_media.vote_average = 8.0
            mock_media.overview = "desc"
            mock_media.runtime = 120
            mock_media.get_poster_image.return_value = "img"
            mock_media.get_detail_url.return_value = "http://tmdb"
            mock_media.get_douban_detail_url.return_value = "http://douban"
            MockWeb.get_mediainfo_from_id.return_value = mock_media
            mock_exists.return_value = (1, "2", "url")
            service._media.get_tmdb_tv_seasons.return_value = [{"season_number": 1}]
            service._media_server.check_item_exists.return_value = True
            service._media.get_tmdb_backdrops.return_value = ["bg1"]
            service._media.get_tmdb_genres_names.return_value = ["Action"]
            service._media.get_tmdb_factinfo.return_value = {}
            service._media.get_tmdb_crews.return_value = []
            service._media.get_tmdb_cats.return_value = []
            MockCfg().get_proxy_image_url.return_value = "http://proxy"
            result = service.get_media_detail(tmdbid="123", mtype_str="MOV")
            assert result["title"] == "Test"
            assert result["fav"] == 1

    def test_get_media_detail_no_info(self, service):
        with patch("app.services.media_service.WebUtils") as MockWeb:
            MockWeb.get_mediainfo_from_id.return_value = None
            result = service.get_media_detail(tmdbid="123", mtype_str="MOV")
            assert result is None


class TestMediaRecommendationService:
    @pytest.fixture
    def service(self):
        mock_media = MagicMock()
        mock_douban = MagicMock()
        mock_bangumi = MagicMock()
        mock_media_server = MagicMock()
        mock_subscribe = MagicMock()
        return MediaRecommendationService(
            media=mock_media,
            douban=mock_douban,
            bangumi=mock_bangumi,
            media_server=mock_media_server,
            subscribe=mock_subscribe,
        )

    def test_get_recommend_items_hot_movies(self, service):
        service._media.get_tmdb_hot_movies.return_value = [{"type": "MOV", "title": "A", "year": "2024", "id": "1"}]
        with patch.object(service, "_get_media_exists_info") as mock_exists:
            mock_exists.return_value = (0, None, "")
            result = service.get_recommend_items({"type": "MOV", "subtype": "hm", "page": 1})
            assert len(result) == 1

    def test_get_recommend_items_search(self, service):
        with patch("app.services.media_service.WebUtils") as MockWeb:
            mock_item = MagicMock()
            mock_item.to_dict.return_value = {"type": "MOV", "title": "B", "year": "2024", "id": "2"}
            MockWeb.search_media_infos.return_value = [mock_item]
            with patch.object(service, "_get_media_exists_info") as mock_exists:
                mock_exists.return_value = (0, None, "")
                result = service.get_recommend_items({"type": "SEARCH", "keyword": "test", "source": "tmdb", "page": 1})
                assert len(result) == 1

    def test_get_recommend_items_downloaded(self, service):
        with patch("app.services.media_service.Downloader") as MockDL:
            mock_item = MagicMock()
            mock_item.TMDBID = "1"
            mock_item.TITLE = "C"
            mock_item.TYPE = "电影"
            mock_item.YEAR = "2024"
            mock_item.VOTE = 8
            mock_item.POSTER = "img"
            mock_item.TORRENT = "t"
            mock_item.DATE = "2024-01-01"
            mock_item.SITE = "site"
            MockDL().get_download_history.return_value = [mock_item]
            with patch.object(service, "_get_media_exists_info") as mock_exists:
                mock_exists.return_value = (0, None, "")
                result = service.get_recommend_items({"type": "DOWNLOADED", "page": 1})
                assert len(result) == 1
                assert result[0]["type"] == "MOV"

    def test_get_recommend_items_trending(self, service):
        service._media.get_tmdb_trending_all_week.return_value = [
            {"type": "MOV", "title": "D", "year": "2024", "id": "3"}
        ]
        with patch.object(service, "_get_media_exists_info") as mock_exists:
            mock_exists.return_value = (0, None, "")
            result = service.get_recommend_items({"type": "TRENDING", "page": 1})
            assert len(result) == 1

    def test_get_recommend_items_discover(self, service):
        service._media.get_tmdb_discover.return_value = [{"type": "MOV", "title": "E", "year": "2024", "id": "4"}]
        with patch.object(service, "_get_media_exists_info") as mock_exists:
            mock_exists.return_value = (0, None, "")
            result = service.get_recommend_items({"type": "DISCOVER", "subtype": "MOV", "page": 1, "params": {}})
            assert len(result) == 1

    def test_get_recommend_items_doubantag(self, service):
        service._douban.get_douban_disover.return_value = [{"type": "MOV", "title": "F", "year": "2024", "id": "5"}]
        with patch.object(service, "_get_media_exists_info") as mock_exists:
            mock_exists.return_value = (0, None, "")
            result = service.get_recommend_items(
                {"type": "DOUBANTAG", "subtype": "MOV", "page": 1, "params": {"sort": "R", "tags": ""}}
            )
            assert len(result) == 1

    def test_get_recommend_items_bangumi(self, service):
        service._bangumi.get_bangumi_calendar.return_value = [{"type": "TV", "title": "G", "year": "2024", "id": "6"}]
        with patch.object(service, "_get_media_exists_info") as mock_exists:
            mock_exists.return_value = (0, None, "")
            result = service.get_recommend_items({"type": "MOV", "subtype": "bangumi", "page": 1, "week": 1})
            assert len(result) == 1

    def test_get_recommend_items_similar(self, service):
        with patch("app.services.media_service.MediaInfoService") as MockInfo:
            MockInfo().get_media_similar.return_value = [{"type": "MOV", "title": "H", "year": "2024", "id": "7"}]
            with patch.object(service, "_get_media_exists_info") as mock_exists:
                mock_exists.return_value = (0, None, "")
                result = service.get_recommend_items({"type": "MOV", "subtype": "sim", "page": 1, "tmdbid": "123"})
                assert len(result) == 1

    def test_convert_downloaded_none(self):
        assert MediaRecommendationService._convert_downloaded(None) == []

    def test_convert_downloaded_items(self):
        mock_item = MagicMock()
        mock_item.TMDBID = "1"
        mock_item.TITLE = "Test"
        mock_item.TYPE = "电影"
        mock_item.YEAR = "2024"
        mock_item.VOTE = 8
        mock_item.POSTER = "img"
        mock_item.TORRENT = "t"
        mock_item.DATE = "2024-01-01"
        mock_item.SITE = "site"
        result = MediaRecommendationService._convert_downloaded([mock_item])
        assert len(result) == 1
        assert result[0]["type"] == "MOV"


class TestSearchResultService:
    @pytest.fixture
    def service(self):
        mock_media_server = MagicMock()
        mock_subscribe = MagicMock()
        return SearchResultService(media_server=mock_media_server, subscribe=mock_subscribe)

    def test_parse_res_type_valid(self):
        result = SearchResultService._parse_res_type(
            json.dumps({"restype": "WEB-DL", "respix": "1080p", "reseffect": "HDR", "video_encode": "H264"})
        )
        assert result == ("WEB-DL", "1080p", "HDR", "H264")

    def test_parse_res_type_invalid(self):
        result = SearchResultService._parse_res_type("not-json")
        assert result == ("", "", "", "")

    def test_parse_res_type_none(self):
        result = SearchResultService._parse_res_type(None)
        assert result == ("", "", "", "")

    def test_group_search_results_empty(self, service):
        result = service.group_search_results([])
        assert result.total == 0
        assert result.result == {}

    def test_group_search_results_single(self, service):
        with patch.object(service, "_get_media_exists_info") as mock_exists:
            mock_exists.return_value = (1, "2", "url")
            mock_item = MagicMock()
            mock_item.ID = "1"
            mock_item.RES_TYPE = json.dumps(
                {"restype": "WEB-DL", "respix": "1080p", "reseffect": "", "video_encode": "H264"}
            )
            mock_item.TITLE = "Test"
            mock_item.YEAR = "2024"
            mock_item.TYPE = "MOV"
            mock_item.ES_STRING = ""
            mock_item.NOTE = "官方|中字"
            mock_item.SIZE = 1024 * 1024 * 1024
            mock_item.OTHERINFO = "Group"
            mock_item.SEEDERS = 100
            mock_item.ENCLOSURE = "enc"
            mock_item.TORRENT_NAME = "Test.torrent"
            mock_item.DESCRIPTION = "desc"
            mock_item.PAGEURL = "url"
            mock_item.UPLOAD_VOLUME_FACTOR = 1.0
            mock_item.DOWNLOAD_VOLUME_FACTOR = 1.0
            mock_item.IMAGE = "img"
            mock_item.POSTER = "poster"
            mock_item.OVERVIEW = "overview"
            mock_item.VOTE = 8.0
            mock_item.TMDBID = "123"
            result = service.group_search_results([mock_item])
            assert result.total == 1
            assert "Test (2024)" in result.result

    def test_merge_into_existing(self, service):
        SearchResults = {
            "Test (2024)": {
                "torrent_dict": {
                    "MOV": {
                        "1080p_webdl": {
                            "group_info": {"respix": "1080p"},
                            "group_total": 1,
                            "group_torrents": {"key1": {"unique_info": {}, "torrent_list": [{"id": "1"}]}},
                        }
                    }
                },
                "filter": {
                    "site": ["SiteA"],
                    "free": [{"value": "1 1", "name": "Free"}],
                    "releasegroup": ["Group"],
                    "video": ["H264"],
                    "season": [],
                },
            }
        }
        mock_item = MagicMock()
        mock_item.SITE = "SiteB"
        mock_item.UPLOAD_VOLUME_FACTOR = 1.0
        mock_item.DOWNLOAD_VOLUME_FACTOR = 1.0
        mock_item.OTHERINFO = "Group2"
        SearchResultService._merge_into_existing(
            SearchResults,
            "Test (2024)",
            "MOV",
            "1080p_webdl",
            "key2",
            {"id": "2"},
            {"respix": "1080p"},
            {"video_encode": "H265"},
            {"value": "1 1", "name": "Free"},
            "Group2",
            "SiteB",
            "H265",
            None,
        )
        assert SearchResults["Test (2024)"]["torrent_dict"]["MOV"]["1080p_webdl"]["group_total"] == 2

    def test_se_sort(self, service):
        assert SearchResultService._se_sort(("S01E01",)) == ("S01", "E01")
        assert SearchResultService._se_sort(("S01",)) == ("ZS01", "ZZZ")


class TestMediaLibraryService:
    @pytest.fixture
    def service(self):
        mock_media_server = MagicMock()
        mock_filetransfer = MagicMock()
        return MediaLibraryService(media_server=mock_media_server, filetransfer=mock_filetransfer)

    def test_get_sync_state_no_status(self, service):
        service._media_server.get_mediasync_status.return_value = None
        assert service.get_sync_state() == "未同步"

    def test_get_sync_state_with_status(self, service):
        service._media_server.get_mediasync_status.return_value = {
            "movie_count": 100,
            "tv_count": 50,
            "time": "2024-01-01",
        }
        result = service.get_sync_state()
        assert "电影：100" in result

    def test_start_sync(self, service):
        with (
            patch("app.services.media_service.TokenCache") as MockCache,
            patch("app.services.media_service.SystemConfig") as MockSys,
            patch("app.services.media_service.ThreadHelper") as MockTh,
        ):
            service.start_sync(librarys=["movies"])
            MockCache.delete.assert_called_once_with("index")

    def test_get_media_count(self, service):
        service._media_server.get_medias_count.return_value = {
            "MovieCount": 100,
            "SeriesCount": 50,
            "EpisodeCount": 200,
            "SongCount": 300,
        }
        service._media_server.get_user_count.return_value = 5
        result = service.get_media_count()
        assert result["Movie"] == "100"
        assert result["User"] == 5

    def test_get_media_count_none(self, service):
        service._media_server.get_medias_count.return_value = None
        assert service.get_media_count() is None

    def test_get_play_history(self, service):
        service._media_server.get_activity_log.return_value = [{"title": "A"}]
        assert service.get_play_history() == [{"title": "A"}]

    def test_get_space_info(self, service):
        with (
            patch("app.services.media_service.Config") as MockCfg,
            patch("app.services.media_service.SystemUtils") as MockSys,
        ):
            MockCfg().get_config.return_value = {"movie_path": ["/movies"], "tv_path": ["/tv"], "anime_path": []}
            MockSys.calculate_space_usage.return_value = (1024, 512)
            result = service.get_space_info()
            assert result.used_percent is not None
            assert "GB" in result.free_space or "TB" in result.free_space

    def test_get_space_info_no_paths(self, service):
        with patch("app.services.media_service.Config") as MockCfg:
            MockCfg().get_config.return_value = {}
            result = service.get_space_info()
            assert result.used_percent == 0

    def test_get_space_info_zero_total(self, service):
        with (
            patch("app.services.media_service.Config") as MockCfg,
            patch("app.services.media_service.SystemUtils") as MockSys,
        ):
            MockCfg().get_config.return_value = {"movie_path": ["/movies"]}
            MockSys.calculate_space_usage.return_value = (0, 0)
            result = service.get_space_info()
            assert result.used_percent == 0


class TestTransferHistoryService:
    @pytest.fixture
    def service(self):
        mock_filetransfer = MagicMock()
        return TransferHistoryService(filetransfer=mock_filetransfer)

    def test_get_transfer_history_page(self, service):
        mock_history = MagicMock()
        mock_history.as_dict.return_value = {"ID": 1, "MODE": "link", "TITLE": "Test"}
        service._filetransfer.get_transfer_history.return_value = (1, [mock_history])
        result = service.get_transfer_history_page(search_str="test", page=1, page_num=10)
        assert result.total == 1
        assert result.current_page == 1
        assert result.page_num == 10

    def test_get_transfer_history_page_defaults(self, service):
        mock_history = MagicMock()
        mock_history.as_dict.return_value = {"ID": 1, "MODE": ""}
        service._filetransfer.get_transfer_history.return_value = (0, [mock_history])
        result = service.get_transfer_history_page(search_str=None, page=None, page_num=None)
        assert result.page_num == 30
        assert result.current_page == 1

    def test_get_transfer_statistics(self, service):
        service._filetransfer.get_transfer_statistics.return_value = [
            ("电影", "2024-01", 5),
            ("电视剧", "2024-01", 3),
            ("动漫", "2024-01", 2),
        ]
        result = service.get_transfer_statistics(days=30)
        assert "Labels" in result
        assert sum(result["MovieNums"]) == 5
        assert sum(result["TvNums"]) == 3
        assert sum(result["AnimeNums"]) == 2

    def test_get_transfer_statistics_skip_zero(self, service):
        service._filetransfer.get_transfer_statistics.return_value = [
            ("电影", "2024-01", 0),
        ]
        result = service.get_transfer_statistics(days=30)
        assert result["Labels"] == []

    def test_get_unknown_list(self, service):
        mock_rec = MagicMock()
        mock_rec.ID = 1
        mock_rec.PATH = "C:\\test\\file.mkv"
        mock_rec.DEST = "D:\\dest"
        mock_rec.MODE = "link"
        service._filetransfer.get_transfer_unknown_paths.return_value = [mock_rec]
        result = service.get_unknown_list()
        assert len(result) == 1
        assert result[0]["path"] == "C:/test/file.mkv"

    def test_get_unknown_list_skip_empty(self, service):
        mock_rec = MagicMock()
        mock_rec.PATH = ""
        service._filetransfer.get_transfer_unknown_paths.return_value = [mock_rec]
        result = service.get_unknown_list()
        assert len(result) == 0

    def test_get_unknown_list_by_page(self, service):
        mock_rec = MagicMock()
        mock_rec.ID = 1
        mock_rec.PATH = "/test/file.mkv"
        mock_rec.DEST = "/dest"
        mock_rec.MODE = "copy"
        service._filetransfer.get_transfer_unknown_paths_by_page.return_value = (1, [mock_rec])
        result = service.get_unknown_list_by_page(search_str="test", page=1, page_num=10)
        assert result.total == 1
        assert result.page_num == 10

    def test_re_identify_unknown(self, service):
        mock_rec = MagicMock()
        mock_rec.ID = 1
        mock_rec.PATH = "/test/file.mkv"
        service._filetransfer.get_transfer_unknown_paths.return_value = [mock_rec]

        mock_sync_mod = MagicMock()
        mock_sync_mod.re_identification = MagicMock()
        import sys

        sys.modules["web.controllers.sync"] = mock_sync_mod
        try:
            count = service.re_identify_unknown()
            assert count == 1
            mock_sync_mod.re_identification.assert_called_once()
        finally:
            sys.modules.pop("web.controllers.sync", None)

    def test_re_identify_unknown_empty(self, service):
        service._filetransfer.get_transfer_unknown_paths.return_value = []

        mock_sync_mod = MagicMock()
        mock_sync_mod.re_identification = MagicMock()
        import sys

        sys.modules["web.controllers.sync"] = mock_sync_mod
        try:
            count = service.re_identify_unknown()
            assert count == 0
            mock_sync_mod.re_identification.assert_not_called()
        finally:
            sys.modules.pop("web.controllers.sync", None)

    def test_clear_history(self, service):
        service.clear_history()
        service._filetransfer.delete_transfer.assert_called_once()
        service._filetransfer.truncate_transfer_blacklist.assert_called_once()


class TestMediaFileService:
    @pytest.fixture
    def service(self):
        return MediaFileService()

    def test_download_subtitle_no_media(self, service):
        with patch("app.services.media_service.Media") as MockMedia:
            MockMedia().get_media_info.return_value = None
            ok, msg = service.download_subtitle("/path", "Test.mkv")
            assert not ok
            assert "无法从TMDB" in msg

    def test_download_subtitle_no_imdb(self, service):
        with (
            patch("app.services.media_service.Media") as MockMedia,
            patch("app.services.media_service.EventManager") as MockEvt,
        ):
            mock_media = MagicMock()
            mock_media.tmdb_info = {"id": 1}
            mock_media.imdb_id = None
            mock_media.tmdb_id = "123"
            mock_media.to_dict.return_value = {"title": "Test"}
            MockMedia().get_media_info.return_value = mock_media
            MockMedia().get_tmdb_info.return_value = {"imdb_id": "tt123"}
            ok, msg = service.download_subtitle("/path/Test.mkv", "Test.mkv")
            assert ok
            assert "字幕下载任务已提交" in msg
            MockEvt().send_event.assert_called_once()

    def test_download_subtitle_with_imdb(self, service):
        with (
            patch("app.services.media_service.Media") as MockMedia,
            patch("app.services.media_service.EventManager") as MockEvt,
        ):
            mock_media = MagicMock()
            mock_media.tmdb_info = {"id": 1}
            mock_media.imdb_id = "tt123"
            mock_media.to_dict.return_value = {"title": "Test"}
            MockMedia().get_media_info.return_value = mock_media
            ok, msg = service.download_subtitle("/path/Test.mkv", "Test.mkv")
            assert ok
            MockEvt().send_event.assert_called_once()

    def test_scrap_media_path_empty(self, service):
        msg = service.scrap_media_path("")
        assert msg == "请指定刮削路径"

    def test_scrap_media_path(self, service):
        with patch("app.services.media_service.ThreadHelper") as MockTh:
            msg = service.scrap_media_path("/media")
            assert "刮削任务已提交" in msg
            MockTh().start_thread.assert_called_once()

    def test_get_category_config_no_name(self, service):
        ok, msg = service.get_category_config("")
        assert not ok
        assert "请输入" in msg

    def test_get_category_config_invalid_name(self, service):
        ok, msg = service.get_category_config("config")
        assert not ok
        assert "非法" in msg

    def test_get_category_config_not_exist(self, service):
        with patch("os.path.exists", return_value=False):
            ok, msg = service.get_category_config("custom")
            assert not ok
            assert "请保存" in msg

    def test_get_category_config_success(self, service):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="movies:\n  - action")),
        ):
            with patch("app.services.media_service.Config") as MockCfg:
                MockCfg().get_config_path.return_value = "/config"
                ok, text = service.get_category_config("custom")
                assert ok
                assert text == "movies:\n  - action"

    def test_update_category_config(self, service):
        with patch("builtins.open", mock_open()) as mock_file, patch("app.services.media_service.Config") as MockCfg:
            MockCfg().category_path = "/config/category.yaml"
            msg = service.update_category_config("content")
            assert msg == "保存成功"
            mock_file.assert_called_once()

    def test_save_user_script(self, service):
        with patch("app.services.media_service.SystemConfig") as MockSys:
            service.save_user_script("alert(1);", "body{color:red}")
            MockSys().set.assert_called_once_with(
                key=SystemConfigKey.CustomScript, value={"css": "body{color:red}", "javascript": "alert(1);"}
            )
