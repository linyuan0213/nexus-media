from app.domain.engine.brush_rule_engine import BrushRuleEngine
from app.utils.types import BrushDeleteType, BrushStopType


class TestBrushRuleEngine:
    # ------------------- check_range_rule -------------------
    def test_check_range_rule_gt(self):
        assert BrushRuleEngine.check_range_rule(5, "gt#3") is True
        assert BrushRuleEngine.check_range_rule(2, "gt#3") is False

    def test_check_range_rule_lt(self):
        assert BrushRuleEngine.check_range_rule(2, "lt#3") is True
        assert BrushRuleEngine.check_range_rule(5, "lt#3") is False

    def test_check_range_rule_bw(self):
        assert BrushRuleEngine.check_range_rule(5, "bw#3,10") is True
        assert BrushRuleEngine.check_range_rule(3, "bw#3,10") is True
        assert BrushRuleEngine.check_range_rule(10, "bw#3,10") is False

    def test_check_range_rule_multiplier(self):
        assert BrushRuleEngine.check_range_rule(2048, "gt#1", multiplier=1024) is True
        assert BrushRuleEngine.check_range_rule(512, "gt#1", multiplier=1024) is False

    def test_check_range_rule_empty_or_invalid(self):
        assert BrushRuleEngine.check_range_rule(0, "") is True
        assert BrushRuleEngine.check_range_rule(0, "gt#") is True
        assert BrushRuleEngine.check_range_rule(None, "gt#1") is True

    # ------------------- _check_free_status -------------------
    def test_check_free_status(self):
        assert BrushRuleEngine._check_free_status({"free": True}, "FREE") is True
        assert BrushRuleEngine._check_free_status({"free": False}, "FREE") is False
        assert BrushRuleEngine._check_free_status({"2xfree": True}, "2XFREE") is True
        assert BrushRuleEngine._check_free_status({"2xfree": False}, "2XFREE") is False
        assert BrushRuleEngine._check_free_status({}, "NORMAL") is True
        assert BrushRuleEngine._check_free_status({"free": True}, "NORMAL") is False

    # ------------------- check_rss_rule -------------------
    def test_check_rss_rule_empty(self):
        assert BrushRuleEngine.check_rss_rule(None, "title", 1, None, {}) is True

    def test_check_rss_rule_size(self):
        rule = {"size": "gt#1"}
        assert BrushRuleEngine.check_rss_rule(rule, "t", 1.5 * 1024 ** 3, None, {}) is True
        assert BrushRuleEngine.check_rss_rule(rule, "t", 0.5 * 1024 ** 3, None, {}) is False

    def test_check_rss_rule_include_exclude(self):
        assert BrushRuleEngine.check_rss_rule({"include": "abc"}, "xxabcxx", 1, None, {}) is True
        assert BrushRuleEngine.check_rss_rule({"include": "abc"}, "xxaxx", 1, None, {}) is False
        assert BrushRuleEngine.check_rss_rule({"exclude": "abc"}, "xxaxx", 1, None, {}) is True
        assert BrushRuleEngine.check_rss_rule({"exclude": "abc"}, "xxabcxx", 1, None, {}) is False

    def test_check_rss_rule_hr(self):
        assert BrushRuleEngine.check_rss_rule({"hr": "HR"}, "t", 1, None, {"hr": False}) is True
        assert BrushRuleEngine.check_rss_rule({"hr": "HR"}, "t", 1, None, {"hr": True}) is False

    def test_check_rss_rule_peercount(self):
        assert BrushRuleEngine.check_rss_rule({"peercount": "lt#10"}, "t", 1, None, {"peer_count": 5}) is True
        assert BrushRuleEngine.check_rss_rule({"peercount": "lt#10"}, "t", 1, None, {"peer_count": 15}) is False

    def test_check_rss_rule_ignore_hash(self):
        assert BrushRuleEngine.check_rss_rule({"size": "#"}, "t", 1, None, {}) is True
        assert BrushRuleEngine.check_rss_rule({"size": "N"}, "t", 1, None, {}) is True

    # ------------------- check_remove_rule -------------------
    def test_check_remove_rule_empty(self):
        need, dtype = BrushRuleEngine.check_remove_rule(None, {})
        assert need is False
        assert dtype == BrushDeleteType.NOTDELETE

    def test_check_remove_rule_or_mode(self):
        rule = {"mode": "or", "time": "gt#10"}
        params = {"seeding_time": 11 * 3600}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is True
        assert dtype == BrushDeleteType.SEEDTIME

    def test_check_remove_rule_and_mode(self):
        rule = {"mode": "and", "time": "gt#10", "ratio": "gt#2"}
        params = {"seeding_time": 11 * 3600, "ratio": 1.5}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is False

        params = {"seeding_time": 11 * 3600, "ratio": 2.5}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is True
        assert BrushDeleteType.SEEDTIME in dtype
        assert BrushDeleteType.RATIO in dtype

    def test_check_remove_rule_hr_time_vs_time(self):
        rule = {"mode": "or", "time": "gt#5", "hr_time": "gt#10"}
        params = {"seeding_time": 6 * 3600, "torrent_attr": {"hr": True}}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is False

        params = {"seeding_time": 11 * 3600, "torrent_attr": {"hr": True}}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is True
        assert dtype == BrushDeleteType.HRSEEDTIME

        params = {"seeding_time": 6 * 3600, "torrent_attr": {"hr": False}}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is True
        assert dtype == BrushDeleteType.SEEDTIME

    def test_check_remove_rule_freestatus(self):
        rule = {"mode": "or", "freestatus": "Y"}
        params = {"torrent_attr": {"free": False}}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is True
        assert dtype == BrushDeleteType.FREEEND

        params = {"torrent_attr": {"free": True}}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is False

    def test_check_remove_rule_ignore_hash(self):
        rule = {"mode": "or", "time": "#"}
        params = {"seeding_time": 1}
        need, dtype = BrushRuleEngine.check_remove_rule(rule, params)
        assert need is False

    # ------------------- check_stop_rule -------------------
    def test_check_stop_rule(self):
        assert BrushRuleEngine.check_stop_rule({"stopfree": "Y"}, {"free": False}) == (True, BrushStopType.FREEEND)
        assert BrushRuleEngine.check_stop_rule({"stopfree": "Y"}, {"free": True}) == (False, BrushStopType.NOTSTOP)
        assert BrushRuleEngine.check_stop_rule(None, {}) == (False, BrushStopType.NOTSTOP)

    # ------------------- format_rule_html -------------------
    def test_format_rule_html_basic(self):
        html = BrushRuleEngine.format_rule_html({"size": "gt#1,10", "dlcount": "5"})
        assert "种子大小" in html
        assert "同时下载" in html

    def test_format_rule_html_peercount_compat(self):
        html = BrushRuleEngine.format_rule_html({"peercount": "10"})
        assert "做种人数" in html
        assert "< 10" in html

    def test_format_rule_html_empty(self):
        assert BrushRuleEngine.format_rule_html(None) == ""
        assert BrushRuleEngine.format_rule_html({}) == ""
