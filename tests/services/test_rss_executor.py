"""Tests for app.services.rss._executor module."""

from unittest.mock import MagicMock, patch

from app.services.rss._executor import _parse_userrss_result


class TestParseUserrssResult:
    """Test suite for _parse_userrss_result function."""

    def test_empty_address_returns_empty_list(self):
        """Empty address list should return empty result."""
        service = MagicMock()
        taskinfo = {"name": "test_task", "address": [], "parser": [1]}
        result = _parse_userrss_result(service, taskinfo)
        assert result == []

    def test_no_parser_returns_empty_list(self):
        """Missing parser should return empty result."""
        service = MagicMock()
        taskinfo = {"name": "test_task", "address": ["http://rss.test"], "parser": []}
        result = _parse_userrss_result(service, taskinfo)
        assert result == []

    def test_invalid_parser_logs_error(self):
        """Invalid parser config should log error and skip."""
        service = MagicMock()
        service.get_userrss_parser.return_value = {}
        taskinfo = {
            "name": "test_task",
            "address": ["http://rss.test"],
            "parser": [1],
        }
        result = _parse_userrss_result(service, taskinfo)
        assert result == []
        service.get_userrss_parser.assert_called_once_with(1)

    @patch("app.services.rss._executor.RequestUtils")
    @patch("app.services.rss._executor.RssParserEngine.parse_items")
    def test_successful_parse(self, mock_parse_items, mock_request_utils):
        """Successful RSS fetch and parse."""
        service = MagicMock()
        service.get_userrss_parser.return_value = {
            "id": 1,
            "name": "test_parser",
            "format": '{"list": "//item"}',
            "params": None,
        }

        mock_response = MagicMock()
        mock_response.text = "<xml>test</xml>"
        mock_request_utils.return_value.get_res.return_value = mock_response
        mock_parse_items.return_value = [{"title": "Test Item"}]

        taskinfo = {
            "name": "test_task",
            "address": ["http://rss.test"],
            "parser": [1],
            "proxy": False,
        }

        result = _parse_userrss_result(service, taskinfo)

        assert len(result) == 1
        assert result[0]["title"] == "Test Item"
        mock_request_utils.return_value.get_res.assert_called_once()
        mock_parse_items.assert_called_once()

    @patch("app.services.rss._executor.RequestUtils")
    def test_request_failure_returns_empty(self, mock_request_utils):
        """Failed HTTP request should return empty result."""
        service = MagicMock()
        service.get_userrss_parser.return_value = {
            "id": 1,
            "name": "test_parser",
            "format": '{"list": "//item"}',
            "params": None,
        }
        mock_request_utils.return_value.get_res.return_value = None

        taskinfo = {
            "name": "test_task",
            "address": ["http://rss.test"],
            "parser": [1],
            "proxy": False,
        }

        result = _parse_userrss_result(service, taskinfo)
        assert result == []
