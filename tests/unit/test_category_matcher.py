"""统一分类映射与旧规则兼容测试."""

from app.media.category_context import CategoryContext
from app.media.category_matcher import get_category, match_category


def test_tmdb_genre_ids_are_normalized():
    categories = {"kids": {"genres": "16,10762"}, "fallback": {}}
    info = {"genres": [{"id": 16, "name": "Animation"}, {"id": 10762, "name": "Kids"}], "original_language": "ja"}
    assert get_category(categories, info, "tv") == "kids"


def test_douban_genre_names_are_normalized():
    categories = {"kids": {"genres": "动画,儿童"}, "fallback": {}}
    info = {"genres": ["动画", "儿童"], "languages": ["日语"], "countries": ["日本"]}
    assert get_category(categories, info, "tv") == "kids"


def test_language_aliases_include_kr_to_ko():
    categories = {"korean": {"original_language": "ja,kr"}, "fallback": {}}
    assert get_category(categories, {"original_language": "ko"}, "tv") == "korean"
    assert get_category(categories, {"original_language": "韓国語"}, "tv") == "korean"


def test_country_names_are_normalized():
    categories = {"japan": {"origin_country": "JP"}}
    assert get_category(categories, {"countries": ["日本"]}, "movie") == "japan"


def test_empty_rules_remain_fallback():
    categories = {"empty": {}, "kids": {"genres": "10762"}}
    assert get_category(categories, {"genres": ["动画"]}, "tv") == "empty"
    assert get_category(categories, {"genres": ["儿童"]}, "tv") == "kids"


def test_context_can_be_merged_for_multiple_sources():
    tmdb = CategoryContext.from_info({"genres": [{"id": 16}], "original_language": "ja"}, media_type="tv")
    douban = CategoryContext.from_info({"genres": ["儿童"], "countries": ["日本"]}, media_type="tv")
    merged = tmdb.merge(douban)
    assert "animation" in merged.genres
    assert "kids" in merged.genres
    assert "ja" in merged.languages
    assert "JP" in merged.countries
    assert match_category({"kids": {"genres": "kids"}}, merged) == "kids"
