"""刮削模块端到端集成测试.

覆盖 _scrape_movie、_scrape_tv、NFO 生成、图片下载、演职人员中文匹配。
"""

import os
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.media.scraper import Scraper


def build_movie_media(tmdb_id=550, title="Fight Club") -> MediaInfo:
    media = MediaInfo()
    media.type = MediaType.MOVIE
    media.tmdb_id = tmdb_id
    media.title = title
    media.original_title = title
    media.year = "1999"
    media.poster_path = "https://image.tmdb.org/t/p/original/poster.jpg"
    media.backdrop_path = "https://image.tmdb.org/t/p/original/backdrop.jpg"
    media.tmdb_info = {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "release_date": "1999-10-15",
        "overview": "An insomniac office worker...",
        "vote_average": 8.4,
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "genres": [{"id": 18, "name": "Drama"}],
        "external_ids": {
            "imdb_id": "tt0137523",
            "tvdb_id": 0,
        },
    }
    return media


def build_tv_media(tmdb_id=1399, title="Game of Thrones") -> MediaInfo:
    media = MediaInfo()
    media.type = MediaType.TV
    media.tmdb_id = tmdb_id
    media.title = title
    media.original_title = title
    media.year = "2011"
    media.poster_path = "https://image.tmdb.org/t/p/original/got_poster.jpg"
    media.backdrop_path = "https://image.tmdb.org/t/p/original/got_backdrop.jpg"
    media.tmdb_info = {
        "id": tmdb_id,
        "name": title,
        "original_name": title,
        "first_air_date": "2011-04-17",
        "overview": "Nine noble families...",
        "vote_average": 8.4,
        "poster_path": "/got_poster.jpg",
        "backdrop_path": "/got_backdrop.jpg",
        "genres": [{"id": 18, "name": "Drama"}, {"id": 10765, "name": "Sci-Fi & Fantasy"}],
        "external_ids": {
            "tvdb_id": 121361,
            "imdb_id": "tt0944947",
        },
    }

    def _get_season_seq():
        return "1"

    def _get_episode_seq():
        return "3"

    media.get_season_seq = _get_season_seq
    media.get_episode_seq = _get_episode_seq
    return media


def build_season_detail() -> dict:
    return {
        "id": 123,
        "air_date": "2011-04-17",
        "overview": "Season 1 overview",
        "poster_path": "/season1_poster.jpg",
        "season_number": 1,
        "episodes": [
            {
                "episode_number": 3,
                "name": "Lord Snow",
                "overview": "Jon Snow begins his training...",
                "air_date": "2011-05-01",
                "vote_average": 8.0,
                "id": 1003,
                "crew": [],
                "guest_stars": [],
            }
        ],
    }


@pytest.fixture
def mock_media_service() -> MagicMock:
    svc = MagicMock()
    svc.get_tmdb_info.return_value = None
    svc.get_tmdb_tv_season_detail.return_value = build_season_detail()
    svc.get_tmdb_directors_actors.return_value = (
        [{"name": "David Fincher", "id": 7467}],
        [
            {"name": "Brad Pitt", "id": 287, "role": "Tyler Durden", "order": 0},
            {"name": "Edward Norton", "id": 819, "role": "The Narrator", "order": 1},
        ],
    )
    svc.get_episode_images.return_value = None
    return svc


@pytest.fixture
def scraper(mock_media_service) -> Scraper:
    mock_config = MagicMock()
    mock_config.get.return_value = None
    mock_config.get_user_local_language = MagicMock(return_value="chinese")
    scraper = Scraper(media_service=mock_media_service, system_config=mock_config)
    scraper._scraper_flag = True
    scraper._scraper_nfo = {
        "movie": {"basic": True, "credits": True},
        "tv": {"basic": True, "credits": True, "season_basic": True, "episode_basic": True, "episode_credits": True},
    }
    scraper._scraper_pic = {
        "movie": {"poster": True, "backdrop": True},
        "tv": {"poster": True, "backdrop": True, "season_poster": True, "episode_thumb": True},
    }
    return scraper


class TestScraperMovieE2E:
    def test_gen_movie_nfo(self, scraper, mock_media_service):
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            movie_dir = os.path.join(tmp, "Fight Club (1999)")
            os.makedirs(movie_dir, exist_ok=True)

            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"  # JPEG magic bytes
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=movie_dir,
                    file_name="Fight Club (1999)",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=True,
                )

            nfo_path = os.path.join(movie_dir, "Fight Club (1999).nfo")
            assert os.path.exists(nfo_path), f"NFO file not found at {nfo_path}"

            tree = ET.parse(nfo_path)
            root = tree.getroot()
            assert root.tag == "movie"
            assert root.findtext("title") == "Fight Club"
            assert root.findtext("tmdbid") == "550"
            assert root.findtext("year") == "1999"
            assert root.findtext("imdbid") == "tt0137523"
            assert root.find("uniqueid[@type='tmdb']") is not None
            assert root.find("uniqueid[@type='imdb']") is not None

            directors = root.findall("director")
            director_names = [d.text for d in directors]
            assert "David Fincher" in director_names

            actors = root.findall("actor")
            actor_names = [a.findtext("name") for a in actors]
            assert "Brad Pitt" in actor_names
            assert "Edward Norton" in actor_names

            poster_path = os.path.join(movie_dir, "poster.jpg")
            assert os.path.exists(poster_path), f"Poster not found at {poster_path}"
            assert os.path.getsize(poster_path) > 0

    def test_gen_movie_nfo_no_override_existing(self, scraper):
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            movie_dir = os.path.join(tmp, "Fight Club (1999)")
            os.makedirs(movie_dir, exist_ok=True)

            existing_nfo = os.path.join(movie_dir, "movie.nfo")
            with open(existing_nfo, "w") as f:
                f.write("<movie><title>Old Title</title></movie>")
            existing_time = os.path.getmtime(existing_nfo)

            scraper.gen_scraper_files(
                media=media,
                dir_path=movie_dir,
                file_name="Fight Club (1999)",
                file_ext=".mkv",
                force=True,
                force_nfo=False,
                force_pic=False,
            )

            assert os.path.getmtime(existing_nfo) == pytest.approx(existing_time, abs=0.1)


class TestScraperTVE2E:
    def test_gen_tv_nfo(self, scraper, mock_media_service):
        media = build_tv_media()

        with tempfile.TemporaryDirectory() as tmp:
            show_dir = os.path.join(tmp, "Game of Thrones (2011)")
            season_dir = os.path.join(show_dir, "Season 01")
            os.makedirs(season_dir, exist_ok=True)

            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=season_dir,
                    file_name="Game of Thrones S01E03",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=True,
                )

            tvshow_nfo = os.path.join(show_dir, "tvshow.nfo")
            assert os.path.exists(tvshow_nfo), f"tvshow.nfo not found at {tvshow_nfo}"
            tree = ET.parse(tvshow_nfo)
            root = tree.getroot()
            assert root.tag == "tvshow"
            assert root.findtext("title") == "Game of Thrones"
            assert root.findtext("tvdbid") == "121361"

            season_nfo = os.path.join(season_dir, "season.nfo")
            assert os.path.exists(season_nfo), f"season.nfo not found at {season_nfo}"
            s_tree = ET.parse(season_nfo)
            s_root = s_tree.getroot()
            assert s_root.tag == "season"
            assert s_root.findtext("seasonnumber") == "1"

            ep_nfo = os.path.join(season_dir, "Game of Thrones S01E03.nfo")
            assert os.path.exists(ep_nfo), f"episode.nfo not found at {ep_nfo}"
            e_tree = ET.parse(ep_nfo)
            e_root = e_tree.getroot()
            assert e_root.tag == "episodedetails"
            assert e_root.findtext("title") == "Lord Snow"
            assert e_root.findtext("episode") == "3"
            assert e_root.findtext("season") == "1"

    def test_season_detail_called_once(self, scraper, mock_media_service):
        """验证 TV 季信息 API 只调用一次（去重修复）"""
        media = build_tv_media()

        with tempfile.TemporaryDirectory() as tmp:
            show_dir = os.path.join(tmp, "Game of Thrones (2011)")
            season_dir = os.path.join(show_dir, "Season 01")
            os.makedirs(season_dir, exist_ok=True)

            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=season_dir,
                    file_name="Game of Thrones S01E03",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=True,
                )

            assert mock_media_service.get_tmdb_tv_season_detail.call_count == 1, (
                f"Expected 1 call, got {mock_media_service.get_tmdb_tv_season_detail.call_count}"
            )


class TestNfoContentCorrectness:
    def test_movie_nfo_genres(self, scraper):
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=tmp,
                    file_name="Fight Club",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=False,
                )

            tree = ET.parse(os.path.join(tmp, "Fight Club.nfo"))
            root = tree.getroot()
            genres = [g.text for g in root.findall("genre")]
            assert "Drama" in genres

    def test_movie_nfo_uniqueid_ordering(self, scraper):
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=tmp,
                    file_name="Fight Club",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=False,
                )

            tree = ET.parse(os.path.join(tmp, "Fight Club.nfo"))
            root = tree.getroot()
            uniqueids = root.findall("uniqueid")
            assert len(uniqueids) >= 2
            assert uniqueids[0].get("type") == "tmdb"

    def test_movie_rating(self, scraper):
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=tmp,
                    file_name="Fight Club",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=False,
                )

            tree = ET.parse(os.path.join(tmp, "Fight Club.nfo"))
            root = tree.getroot()
            rating = root.findtext("rating")
            assert rating is not None
            assert float(rating) == 8.4


class TestImageDownloadExtension:
    def test_poster_saved_as_jpg(self, scraper):
        """验证图片通过 Content-Type 推断扩展名保存为 .jpg"""
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=tmp,
                    file_name="test",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=True,
                )

            assert os.path.exists(os.path.join(tmp, "poster.jpg"))
            assert os.path.exists(os.path.join(tmp, "fanart.jpg"))

    def test_poster_without_content_type_fallback_to_url_extension(self, scraper):
        media = build_movie_media()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_resp = MagicMock()
                mock_resp.content = b"\xff\xd8\xff\xe0"
                mock_resp.headers = {}
                mock_http.return_value.get.return_value = mock_resp

                scraper.gen_scraper_files(
                    media=media,
                    dir_path=tmp,
                    file_name="test",
                    file_ext=".mkv",
                    force=True,
                    force_nfo=True,
                    force_pic=True,
                )

            # poster_path is "/poster.jpg", so URL-based extension should be .jpg
            assert os.path.exists(os.path.join(tmp, "poster.jpg"))
