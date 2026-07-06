"""刮削模块单元测试."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from app.media.scraper.chinese_credits import ChineseCredits
from app.media.scraper.image_downloader import ImageDownloader


class TestImageDownloaderExtension:
    def test_guess_extension_from_url_path(self):
        assert ImageDownloader._guess_extension("https://example.com/poster.jpg") == ".jpg"
        assert ImageDownloader._guess_extension("https://example.com/backdrop.png?w=500") == ".png"

    def test_guess_extension_no_dot_fallback(self):
        assert ImageDownloader._guess_extension("https://image.tmdb.org/t/p/original/abc123") == ".jpg"

    def test_guess_extension_query_only_no_path(self):
        assert ImageDownloader._guess_extension("https://example.com/?image=abc") == ".jpg"

    def test_resolve_extension_from_content_type(self):
        result = ImageDownloader._resolve_extension("/out/poster.xyz", "image/png")
        assert result == "/out/poster.png"

    def test_resolve_extension_unknown_content_type(self):
        result = ImageDownloader._resolve_extension("/out/fanart.jpg", "application/octet-stream")
        assert result == "/out/fanart.jpg"

    def test_resolve_extension_content_type_with_charset(self):
        result = ImageDownloader._resolve_extension("/out/backdrop.webp", "image/jpeg; charset=utf-8")
        assert result == "/out/backdrop.jpg"

    def test_resolve_extension_all_types(self):
        for ct, ext in [
            ("image/jpeg", ".jpg"),
            ("image/png", ".png"),
            ("image/webp", ".webp"),
            ("image/gif", ".gif"),
            ("image/bmp", ".bmp"),
            ("image/tiff", ".tiff"),
            ("image/svg+xml", ".svg"),
        ]:
            result = ImageDownloader._resolve_extension("/out/img.bin", ct)
            assert result == f"/out/img{ext}"

    def test_download_saves_with_correct_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = ImageDownloader(tmp)
            with patch("app.media.scraper.image_downloader.HttpClient") as mock_http:
                mock_response = MagicMock()
                mock_response.content = b"fake-jpeg"
                mock_response.headers = {"content-type": "image/jpeg"}
                mock_http.return_value.get.return_value = mock_response

                downloader.download("https://example.com/t/p/original/abc123", tmp, "poster")

                mock_http.return_value.get.assert_called_once_with(
                    url="https://example.com/t/p/original/abc123", raise_exception=True
                )
                poster_path = os.path.join(tmp, "poster.jpg")
                assert os.path.exists(poster_path)
                with open(poster_path, "rb") as f:
                    assert f.read() == b"fake-jpeg"


class TestChineseCredits:
    def test_match_no_douban_info(self):
        svc = MagicMock()
        credits = ChineseCredits(svc)
        directors, actors = credits.match([{"name": "John"}], [{"name": "Jane"}], None)
        assert directors == [{"name": "John"}]
        assert actors == [{"name": "Jane"}]

    def test_match_empty_douban_info(self):
        svc = MagicMock()
        credits = ChineseCredits(svc)
        directors, actors = credits.match([{"name": "John"}], [{"name": "Jane"}], {})
        assert directors == [{"name": "John"}]
        assert actors == [{"name": "Jane"}]

    def test_match_director_by_latin_name(self):
        svc = MagicMock()
        svc.get_tmdbperson_aka_names.return_value = ["Christopher Nolan"]
        credits = ChineseCredits(svc)

        douban = {
            "directors": [{"name": "克里斯托弗·诺兰", "latin_name": "Christopher Nolan"}],
            "actors": [],
        }
        directors, _ = credits.match([{"name": "Christopher Nolan", "id": 1}], [], douban)
        assert directors[0]["name"] == "克里斯托弗·诺兰"

    def test_match_actor_by_aka_name(self):
        svc = MagicMock()
        svc.get_tmdbperson_aka_names.return_value = ["Leonardo DiCaprio", "Leo"]
        credits = ChineseCredits(svc)

        douban = {
            "directors": [],
            "actors": [{"name": "莱昂纳多·迪卡普里奥", "latin_name": "Leonardo DiCaprio", "character": "饰 杰克"}],
        }
        _, actors = credits.match([], [{"name": "Leonardo DiCaprio", "id": 2}], douban)
        assert actors[0]["name"] == "莱昂纳多·迪卡普里奥"

    def test_match_no_latin_name_fallback_to_name(self):
        svc = MagicMock()
        svc.get_tmdbperson_aka_names.return_value = []
        credits = ChineseCredits(svc)

        douban = {"directors": [{"name": "王家卫", "latin_name": ""}], "actors": []}
        directors, _ = credits.match([{"name": "王家卫", "id": 3}], [], douban)
        assert directors[0]["name"] == "王家卫"

    def test_match_character_cleaning(self):
        svc = MagicMock()
        svc.get_tmdbperson_aka_names.return_value = ["Tom Hanks"]
        credits = ChineseCredits(svc)

        douban = {
            "directors": [],
            "actors": [{"name": "汤姆·汉克斯", "latin_name": "Tom Hanks", "character": "饰 Forrest Gump"}],
        }
        _, actors = credits.match([], [{"name": "Tom Hanks", "id": 4}], douban)
        assert actors[0]["name"] == "汤姆·汉克斯"
        assert actors[0]["character"] == "Forrest Gump"


class TestNfoGenerator:
    def test_gen_season_nfo(self):
        from app.media.scraper.nfo_generator import NfoGenerator

        mock_dl = MagicMock()
        gen = NfoGenerator(mock_dl)

        seasoninfo = {"overview": "A great season", "air_date": "2024-01-01"}
        with tempfile.TemporaryDirectory() as tmp:
            gen.gen_season_nfo(seasoninfo, 1, tmp)

            mock_dl.save_nfo.assert_called_once()
            doc, out_path = mock_dl.save_nfo.call_args[0]
            assert os.path.basename(out_path) == "season.nfo"
            assert os.path.dirname(out_path) == tmp

    def test_gen_episode_nfo(self):
        from app.media.scraper.nfo_generator import NfoGenerator

        mock_dl = MagicMock()
        gen = NfoGenerator(mock_dl)

        episode = {
            "episode_number": 3,
            "name": "Test Episode",
            "overview": "Test overview",
            "air_date": "2024-01-15",
            "vote_average": 8.5,
            "id": 1001,
            "crew": [],
            "guest_stars": [],
        }
        seasoninfo = {"episodes": [episode]}
        scraper_nfo = {"episode_basic": True, "episode_credits": True}
        with tempfile.TemporaryDirectory() as tmp:
            gen.gen_episode_nfo(seasoninfo, scraper_nfo, 1, 3, tmp, "S01E03")

            mock_dl.save_nfo.assert_called_once()
            doc, out_path = mock_dl.save_nfo.call_args[0]
            assert os.path.basename(out_path) == "S01E03.nfo"

    def test_gen_episode_nfo_not_found(self):
        from app.media.scraper.nfo_generator import NfoGenerator

        mock_dl = MagicMock()
        gen = NfoGenerator(mock_dl)

        seasoninfo = {"episodes": [{"episode_number": 1, "name": "Pilot"}]}
        scraper_nfo = {"episode_basic": True}
        with tempfile.TemporaryDirectory() as tmp:
            gen.gen_episode_nfo(seasoninfo, scraper_nfo, 1, 99, tmp, "S01E99")
            mock_dl.save_nfo.assert_not_called()


class TestMediaLibrary:
    def test_get_tmdbid_from_nfo_found(self):
        from app.media.scraper.media_library import MediaLibrary

        nfo_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <uniqueid type="tmdb" default="true">12345</uniqueid>
        </movie>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nfo", delete=False) as f:
            f.write(nfo_content)
            nfo_path = f.name

        try:
            result = MediaLibrary.get_tmdbid_from_nfo(nfo_path)
            assert result == "12345"
        finally:
            os.unlink(nfo_path)

    def test_get_tmdbid_from_nfo_uppercase_type(self):
        from app.media.scraper.media_library import MediaLibrary

        nfo_content = """<?xml version="1.0" encoding="utf-8"?>
        <tvshow>
            <uniqueid type="TMDB">67890</uniqueid>
        </tvshow>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nfo", delete=False) as f:
            f.write(nfo_content)
            nfo_path = f.name

        try:
            result = MediaLibrary.get_tmdbid_from_nfo(nfo_path)
            assert result == "67890"
        finally:
            os.unlink(nfo_path)

    def test_get_tmdbid_from_nfo_not_found(self):
        from app.media.scraper.media_library import MediaLibrary

        nfo_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>No ID Here</title>
        </movie>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nfo", delete=False) as f:
            f.write(nfo_content)
            nfo_path = f.name

        try:
            result = MediaLibrary.get_tmdbid_from_nfo(nfo_path)
            assert result is None
        finally:
            os.unlink(nfo_path)

    def test_get_tmdbid_from_nfo_tmdbid_element(self):
        from app.media.scraper.media_library import MediaLibrary

        nfo_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <tmdbid>11111</tmdbid>
        </movie>"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nfo", delete=False) as f:
            f.write(nfo_content)
            nfo_path = f.name

        try:
            result = MediaLibrary.get_tmdbid_from_nfo(nfo_path)
            assert result == "11111"
        finally:
            os.unlink(nfo_path)
