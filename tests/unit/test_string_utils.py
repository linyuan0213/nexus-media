"""StringUtils 单元测试"""

from app.utils.string_utils import StringUtils


class TestStringUtils:
    def test_is_chinese(self):
        assert StringUtils.is_chinese("中") is True
        assert StringUtils.is_chinese("a") is False
        assert StringUtils.is_chinese("1") is False

    def test_is_all_chinese(self):
        assert StringUtils.is_all_chinese("中文") is True
        assert StringUtils.is_all_chinese("中文abc") is False

    def test_is_numeric(self):
        assert StringUtils.is_numeric("123") is True
        assert StringUtils.is_numeric("12.3") is True
        assert StringUtils.is_numeric("abc") is False

    def test_clear_file_name(self):
        result = StringUtils.clear_file_name("Movie.Title.2024.1080p.mp4")
        assert result is not None
        assert "Movie" in result or "Title" in result

    def test_generate_random_str(self):
        s1 = StringUtils.generate_random_str(8)
        s2 = StringUtils.generate_random_str(8)
        assert len(s1) == 8
        assert len(s2) == 8
        assert s1 != s2

    def test_to_bool(self):
        assert StringUtils.to_bool("true") is True
        assert StringUtils.to_bool("True") is True
        assert StringUtils.to_bool("1") is True
        assert StringUtils.to_bool("false") is False
        assert StringUtils.to_bool("0") is False
        assert StringUtils.to_bool("") is False

    def test_xstr(self):
        assert StringUtils.xstr("hello") == "hello"
        assert StringUtils.xstr(None) == ""
        assert StringUtils.xstr(123) == 123

    def test_get_base_url(self):
        assert StringUtils.get_base_url("https://example.com/path") == "https://example.com"
        assert StringUtils.get_base_url("http://localhost:3000/api") == "http://localhost:3000"

    def test_md5_hash(self):
        h1 = StringUtils.md5_hash("test")
        h2 = StringUtils.md5_hash("test")
        h3 = StringUtils.md5_hash("different")
        assert h1 == h2
        assert len(h1) == 32
        assert h1 != h3

    def test_str_int(self):
        assert StringUtils.str_int("1,234") == 1234
        assert StringUtils.str_int("abc") == 0
        assert StringUtils.str_int("100") == 100

    def test_str_float(self):
        assert StringUtils.str_float("1.5") == 1.5
        assert StringUtils.str_float("abc") == 0.0

    def test_url_equal(self):
        assert StringUtils.url_equal("https://a.com", "https://a.com/") is True
        assert StringUtils.url_equal("https://a.com", "https://b.com") is False

    def test_handler_special_chars(self):
        result = StringUtils.handler_special_chars("hello: world / test")
        assert ":" not in result
        assert "/" not in result
