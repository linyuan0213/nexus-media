"""测试综合评分引擎 + 批量关键词检测"""

import pytest

from app.media.lookup.tmdb_lookup import _BATCH_KEYWORDS_RE
from app.media.lookup.tmdb_search import _STOP_TOKENS, _score_fuzzy_match, _tokenize


class TestScoreFuzzyMatch:
    def test_exact_name_match(self):
        score = _score_fuzzy_match(
            "Ghost In The Shell",
            {"number_of_episodes": 26, "number_of_seasons": 2},
            ["Ghost in the Shell", "攻壳机动队"],
        )
        assert score > 0.95

    def test_fuzzy_name_different_score(self):
        high = _score_fuzzy_match(
            "Ghost In The Shell S.A.C. 2Nd Gig",
            {"number_of_episodes": 52, "number_of_seasons": 2, "seasons": []},
            ["Ghost in the Shell: S.A.C. 2nd GIG", "攻壳机动队"],
        )
        low = _score_fuzzy_match(
            "Ghost In The Shell S.A.C. 2Nd Gig",
            {"number_of_episodes": 10, "number_of_seasons": 1, "seasons": []},
            ["Ghost in the Shell: S.A.C. 2nd GIG - Individual Eleven"],
        )
        assert high > low, f"精确匹配应高于带后缀的匹配: {high:.3f} vs {low:.3f}"

    def test_season_bonus_matters(self):
        with_season = _score_fuzzy_match(
            "Test Show",
            {"number_of_episodes": 10, "number_of_seasons": 1, "seasons": [{"season_number": 2, "episode_count": 12}]},
            ["Test Show"],
            season_number=2,
        )
        without_season = _score_fuzzy_match(
            "Test Show",
            {"number_of_episodes": 10, "number_of_seasons": 1, "seasons": []},
            ["Test Show"],
            season_number=2,
        )
        assert with_season > without_season, "有目标季号的条目得分应更高"

    def test_season_penalty_for_mismatch(self):
        base = _score_fuzzy_match(
            "Test Show",
            {"number_of_episodes": 10, "number_of_seasons": 1, "seasons": []},
            ["Test Show"],
        )
        penalty = _score_fuzzy_match(
            "Test Show",
            {"number_of_episodes": 10, "number_of_seasons": 1, "seasons": []},
            ["Test Show"],
            season_number=3,
        )
        assert penalty < base, "季号不匹配应有惩罚"

    def test_established_bonus(self):
        many_eps = _score_fuzzy_match(
            "Test Show",
            {"number_of_episodes": 52, "number_of_seasons": 2},
            ["Test Show"],
        )
        few_eps = _score_fuzzy_match(
            "Test Show",
            {"number_of_episodes": 10, "number_of_seasons": 1},
            ["Test Show"],
        )
        assert many_eps > few_eps, "多集数条目应获得已完结加分"

    def test_keyword_bonus(self):
        with_kw = _score_fuzzy_match(
            "Ghost In The Shell SAC 2045",
            {"number_of_episodes": 24, "number_of_seasons": 2},
            ["Ghost in the Shell: SAC_2045", "攻壳机动队 SAC_2045"],
        )
        no_kw = _score_fuzzy_match(
            "Ghost In The Shell",
            {"number_of_episodes": 24, "number_of_seasons": 2},
            ["Ghost in the Shell", "攻壳机动队"],
        )
        assert with_kw > no_kw, "有关键词重叠的条目得分应更高"


class TestTokenize:
    def test_tokenize_simple(self):
        tokens = _tokenize("Ghost In The Shell SAC 2045")
        assert "GHOST" in tokens
        assert "SHELL" in tokens
        assert "SAC" in tokens
        assert "2045" in tokens

    def test_tokenize_stopword_filtered(self):
        tokens = _tokenize("The Ghost In The Shell") - _STOP_TOKENS
        assert "GHOST" in tokens
        assert "SHELL" in tokens
        assert "THE" not in tokens


class TestBatchKeywordsRE:
    BATCH_PATTERNS = [
        ("[POPGO][Ghost][S.A.C._2nd_GIG][COMPLETE][1080P]", True),
        ("[Group] Anime Title 全集 [BD 1080p]", True),
        ("[Group] Anime 合集 BDRip", True),
        ("[Group] Show S1 PACK 1080p", True),
        ("[Group] Movie BATCH HEVC", True),
        ("[Group] Season 3 COLLECTION", True),
        ("[Group] 全季 1080p", True),
        ("[Group] Just A Movie [1080P]", False),
        ("[LoliHouse] Ghost in the Shell - 01 [WebRip]", False),
        ("[POPGO][S.A.C._2nd_GIG][BDRIP][1080P]", False),
        ("Complete Series BluRay", True),
    ]

    @pytest.mark.parametrize("title,expected", BATCH_PATTERNS)
    def test_batch_keyword_detection(self, title, expected):
        result = bool(_BATCH_KEYWORDS_RE.search(title))
        assert result == expected, f"title={title!r}"
