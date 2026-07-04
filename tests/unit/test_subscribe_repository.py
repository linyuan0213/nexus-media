"""Tests for app.db.repositories.subscribe_repository update defaults."""

from unittest.mock import MagicMock, patch

from app.db.repositories.subscribe_repository import SubscribeRepository


class TestSubscribeRepositoryUpdateDefaults:
    """Test suite for update_rss_movie/update_rss_tv None handling."""

    @patch("app.db.repositories.subscribe_repository.JsonUtils.dumps", return_value='"[]"')
    def test_update_rss_movie_replaces_none_with_defaults(self, _mock_dumps):
        repo = SubscribeRepository()
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.__enter__.return_value.query.return_value = mock_query

        with patch.object(repo, "session", return_value=mock_session):
            repo.update_rss_movie(
                rssid=1,
                name="Test",
                save_path=None,
                filter_rule=None,
                download_setting=None,
                fuzzy_match=None,
                over_edition=None,
                rss_sites=["site"],
            )

        update_fields = mock_query.filter.return_value.update.call_args[0][0]
        assert update_fields["SAVE_PATH"] == ""
        assert update_fields["FILTER_RULE"] == 0
        assert update_fields["DOWNLOAD_SETTING"] == -1
        assert update_fields["FUZZY_MATCH"] == 0
        assert update_fields["OVER_EDITION"] == 0
        assert update_fields["NAME"] == "Test"

    @patch("app.db.repositories.subscribe_repository.JsonUtils.dumps", return_value='"[]"')
    def test_update_rss_tv_replaces_none_with_defaults(self, _mock_dumps):
        repo = SubscribeRepository()
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.__enter__.return_value.query.return_value = mock_query

        with patch.object(repo, "session", return_value=mock_session):
            repo.update_rss_tv(
                rssid=1,
                name="Test",
                season=None,
                save_path=None,
                filter_rule=None,
                download_setting=None,
                total_ep=None,
                current_ep=None,
                total=None,
                lack=None,
            )

        update_fields = mock_query.filter.return_value.update.call_args[0][0]
        assert update_fields["SEASON"] == ""
        assert update_fields["SAVE_PATH"] == ""
        assert update_fields["FILTER_RULE"] == 0
        assert update_fields["DOWNLOAD_SETTING"] == -1
        assert update_fields["TOTAL_EP"] == 0
        assert update_fields["CURRENT_EP"] == 0
        assert update_fields["TOTAL"] == 0
        assert update_fields["LACK"] == 0
        assert update_fields["NAME"] == "Test"
