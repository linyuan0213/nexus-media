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


def test_chinese_dialect_names_map_to_zh():
    categories = {"chinese": {"original_language": "zh"}, "fallback": {}}
    for value in ("汉语普通话", "普通话", "粤语", "Cantonese", "Mandarin"):
        assert get_category(categories, {"languages": [value]}, "movie") == "chinese"


def test_tibetan_and_zhuang_codes_match_legacy_rule():
    categories = {"chinese": {"original_language": "zh,cn,bo,za"}, "fallback": {}}
    assert get_category(categories, {"original_language": "bo"}, "movie") == "chinese"
    assert get_category(categories, {"languages": ["藏语"]}, "movie") == "chinese"
    assert get_category(categories, {"original_language": "za"}, "movie") == "chinese"


def test_country_names_are_normalized():
    categories = {"japan": {"origin_country": "JP"}}
    assert get_category(categories, {"countries": ["日本"]}, "movie") == "japan"


def test_douban_mainland_china_alias_maps_to_cn():
    categories = {"cn": {"origin_country": "CN,TW,HK"}, "fallback": {}}
    assert get_category(categories, {"countries": ["中国大陆"]}, "tv") == "cn"
    assert get_category(categories, {"countries": ["中国香港"]}, "tv") == "cn"
    assert get_category(categories, {"countries": ["中国台湾"]}, "tv") == "cn"


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


def test_rule_dsl_supports_operators_and_source():
    context = CategoryContext.from_info(
        {
            "genres": [{"id": 16, "name": "Animation"}],
            "original_language": "ja",
            "content_profile": "demo",
        },
        media_type="tv",
        source="tmdb",
    )
    rules = {
        "anime_ja_demo": [
            {"field": "genre", "operator": "contains", "value": "animation"},
            {"field": "original_language", "operator": "in", "value": ["ja", "ko"]},
            {"field": "content_profile", "operator": "eq", "value": "demo"},
            {"source": "tmdb", "field": "genre", "operator": "contains", "value": "animation"},
        ],
        "fallback": [],
    }
    assert match_category(rules, context) == "anime_ja_demo"


def test_rule_dsl_source_mismatch_does_not_match():
    context = CategoryContext.from_info({"genres": ["动画"]}, source="douban")
    rules = {
        "only_tmdb": [
            {"field": "genre", "operator": "contains", "value": "动画", "source": "tmdb"},
        ],
        "fallback": [],
    }
    assert match_category(rules, context) == "fallback"
