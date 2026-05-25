"""Tokens 解析单元测试"""

from app.utils.tokens import Tokens


class TestTokens:
    def test_simple_title(self):
        tokens = Tokens("Movie Title 2024")
        assert tokens.cur() == "Movie"
        assert tokens.get_next() == "Movie"
        assert tokens.cur() == "Title"

    def test_brackets_and_tags(self):
        title = "[Group] Movie Title - 01 [1080p][x264]"
        tokens = Tokens(title)
        assert "Group" in tokens._tokens
        assert "Movie" in tokens._tokens
        assert "Title" in tokens._tokens
        assert "01" in tokens._tokens
        assert "1080p" in tokens._tokens
        assert "x264" in tokens._tokens

    def test_decimal_replace(self):
        title = "Title 1.5 something"
        tokens = Tokens(title)
        assert "1" in tokens._tokens
        assert "5" in tokens._tokens

    def test_empty_string(self):
        tokens = Tokens("")
        assert tokens.cur() is None
        assert tokens.get_next() is None

    def test_peek(self):
        tokens = Tokens("one two three")
        assert tokens.cur() == "one"
        assert tokens.peek() == "two"
        assert tokens.cur() == "one"
        tokens.get_next()
        assert tokens.cur() == "two"

    def test_only_special_chars(self):
        tokens = Tokens("[ ] - / .")
        assert tokens._tokens == []

    def test_numeric_tokens(self):
        tokens = Tokens("Episode 12 1080p")
        assert "12" in tokens._tokens
        assert "1080p" in tokens._tokens

    def test_chinese_title(self):
        tokens = Tokens("电影名称.2024.1080p")
        assert "电影名称" in tokens._tokens
        assert "2024" in tokens._tokens
