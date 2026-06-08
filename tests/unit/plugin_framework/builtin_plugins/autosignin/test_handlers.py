from unittest.mock import MagicMock, patch

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers._types import BakatestQaHandler


class TestBakatestQaHandler:
    def test_name_and_answer_file(self):
        class TestHandler(BakatestQaHandler):
            site_url = "test.site"
            _name = "test"

        handler = TestHandler(MagicMock())
        assert "test.json" in handler._answer_file

    def test_build_ai_question(self):
        question = "这是什么电影"
        answers = [("1", "选项A"), ("2", "选项B")]
        result = BakatestQaHandler._build_ai_question(question, answers)
        assert "这是什么电影" in result
        assert "1:选项A" in result
        assert "2:选项B" in result

    def test_lookup_local_answer_not_found(self):
        class TestHandler(BakatestQaHandler):
            site_url = "test.site"
            _name = "test"

            @property
            def _answer_file(self) -> str:
                return "/nonexistent/path.json"

        handler = TestHandler(MagicMock())
        result = handler._lookup_local_answer("question", [("1", "A")])
        assert result == []

    @patch("builtins.open")
    def test_lookup_local_answer_found(self, mock_open):
        mock_open.return_value.__enter__.return_value.read.return_value = '{"question": [1]}'

        class TestHandler(BakatestQaHandler):
            site_url = "test.site"
            _name = "test"

            @property
            def _answer_file(self) -> str:
                return "/fake/path.json"

        handler = TestHandler(MagicMock())
        result = handler._lookup_local_answer("question", [("1", "A")])
        assert result == [1]
