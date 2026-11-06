"""RSS 订阅关键词预筛测试."""

from app.services.subscribe.strategies.rss_feed import RssFeedStrategy


def test_subscription_keywords_support_multiple_aliases():
    terms = RssFeedStrategy._subscription_keywords(
        {
            1: {"name": "Song One", "keyword": "一曲倾情"},
            2: {"name": "葬送的芙莉莲 第二季", "keyword": ""},
            3: {"name": "Song One", "aliases": ["第一支歌", "纽约情弦"]},
        }
    )
    assert "SONGONE" in terms
    assert "一曲倾情" in terms
    assert "葬送的芙莉莲" in terms
    assert "第一支歌" in terms
    assert "纽约情弦" in terms


def test_title_matches_any_subscription_keyword():
    terms = RssFeedStrategy._subscription_keywords({1: {"name": "Song One", "keyword": "一曲倾情 / 第一支歌"}})
    title = "Song One 2014 1080p HKG Blu-ray AVC TrueHD 5.1-badboy[一曲倾情 / 第一支歌 / 纽约情弦(港) / 纽约安可曲(台)]"
    assert RssFeedStrategy._title_matches_keywords(title, terms) is True


def test_unmatched_title_is_filtered_without_metadata_call():
    terms = RssFeedStrategy._subscription_keywords({1: {"name": "Song One"}})
    assert RssFeedStrategy._title_matches_keywords("Another.Movie.2024.1080p.BluRay", terms) is False


def test_empty_keywords_does_not_block_identification():
    assert RssFeedStrategy._title_matches_keywords("Anything", set()) is True
