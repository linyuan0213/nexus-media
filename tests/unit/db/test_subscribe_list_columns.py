"""订阅列表型列必须为 TEXT（varchar(255) 会存不下长集号/站点列表）."""

from sqlalchemy import Text

from app.db.models.subscribe import SubscribeMovies, SubscribeTvEpisodes, SubscribeTvs


def _type_name(column):
    return type(column.type).__name__


def test_tv_episodes_is_text():
    assert isinstance(SubscribeTvEpisodes.__table__.c.EPISODES.type, Text), _type_name(
        SubscribeTvEpisodes.__table__.c.EPISODES
    )


def test_tv_sites_are_text():
    for column in ("RSS_SITES", "SEARCH_SITES"):
        assert isinstance(getattr(SubscribeTvs.__table__.c, column).type, Text), (
            column,
            _type_name(getattr(SubscribeTvs.__table__.c, column)),
        )


def test_movie_sites_are_text():
    for column in ("RSS_SITES", "SEARCH_SITES"):
        assert isinstance(getattr(SubscribeMovies.__table__.c, column).type, Text), (
            column,
            _type_name(getattr(SubscribeMovies.__table__.c, column)),
        )
