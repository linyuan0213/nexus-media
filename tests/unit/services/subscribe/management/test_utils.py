"""Subscribe management utils 单元测试."""

from unittest.mock import MagicMock

from app.services.subscribe.management.utils import gen_rss_note, parse_rss_desc


class TestParseRssDesc:
    def test_empty(self):
        assert parse_rss_desc("") == {}
        assert parse_rss_desc(None) == {}

    def test_valid_json(self):
        assert parse_rss_desc('{"key": "value"}') == {"key": "value"}


class TestGenRssNote:
    def test_empty_media(self):
        assert gen_rss_note(None) == "{}"

    def test_with_media(self):
        media = MagicMock()
        media.get_poster_image.return_value = "http://poster.jpg"
        media.release_date = "2024-01-01"
        media.vote_average = 8.5
        note = gen_rss_note(media)
        assert '"poster": "http://poster.jpg"' in note
        assert '"vote": 8.5' in note
