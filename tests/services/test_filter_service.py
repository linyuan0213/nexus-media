import pytest
from unittest.mock import MagicMock, patch

from app.services.filter_service import FilterRuleEngine, FilterService
from app.utils.types import MediaType


class FakeMeta:
    """用于测试的简易 MetaInfo 替身"""
    def __init__(self,
                 rev_string="Test.Title.2024.1080p.WEB-DL",
                 subtitle="",
                 size=None,
                 type=None,
                 total_episodes=None,
                 upload_volume_factor=1.0,
                 download_volume_factor=1.0,
                 org_string=None,
                 resource_pix="",
                 resource_team=""):
        self.rev_string = rev_string
        self.subtitle = subtitle
        self.size = size
        self.type = type or MediaType.MOVIE
        self.total_episodes = total_episodes
        self.upload_volume_factor = upload_volume_factor
        self.download_volume_factor = download_volume_factor
        self.org_string = org_string or rev_string
        self.resource_pix = resource_pix
        self.resource_team = resource_team

    def get_season_list(self):
        return []

    def get_episode_list(self):
        return []

    def get_edtion_string(self):
        return self.rev_string

    def get_volume_factor_string(self):
        return ""


class TestFilterRuleEngineCheckRules:
    def test_empty_meta_returns_false(self):
        assert FilterRuleEngine.check_rules(None, {}, []) == (False, 0, "")

    def test_no_filters_returns_group_match(self):
        meta = FakeMeta()
        assert FilterRuleEngine.check_rules(meta, {"name": "Default"}, []) == (True, 0, "Default")

    def test_include_match(self):
        meta = FakeMeta(rev_string="Test.Title.2024")
        filters = [{"pri": 10, "include": ["test"], "exclude": [], "size": None, "free": None}]
        assert FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)[0] is True

    def test_include_miss(self):
        meta = FakeMeta(rev_string="Another.Title.2024")
        filters = [{"pri": 10, "include": ["test"], "exclude": [], "size": None, "free": None}]
        ok, _, name = FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)
        assert ok is False
        assert name == "Group"

    def test_exclude_match(self):
        meta = FakeMeta(rev_string="Test.Title.BAD.2024")
        filters = [{"pri": 10, "include": [], "exclude": ["bad"], "size": None, "free": None}]
        ok, _, name = FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)
        assert ok is False

    def test_size_movie_range(self):
        meta = FakeMeta(type=MediaType.MOVIE, size="2 GB")
        filters = [{"pri": 10, "include": [], "exclude": [], "size": "1,3", "free": None}]
        assert FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)[0] is True

    def test_size_movie_out_of_range(self):
        meta = FakeMeta(type=MediaType.MOVIE, size="5 GB")
        filters = [{"pri": 10, "include": [], "exclude": [], "size": "1,3", "free": None}]
        assert FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)[0] is False

    def test_free_rule_match(self):
        meta = FakeMeta(upload_volume_factor=1.0, download_volume_factor=0.0)
        filters = [{"pri": 10, "include": [], "exclude": [], "size": None, "free": "1.0 0.0"}]
        assert FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)[0] is True

    def test_free_rule_mismatch(self):
        meta = FakeMeta(upload_volume_factor=1.0, download_volume_factor=1.0)
        filters = [{"pri": 10, "include": [], "exclude": [], "size": None, "free": "1.0 0.0"}]
        assert FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)[0] is False

    def test_priority_order(self):
        meta = FakeMeta(rev_string="Test")
        filters = [
            {"pri": 20, "include": ["nomatch"], "exclude": [], "size": None, "free": None},
            {"pri": 10, "include": ["test"], "exclude": [], "size": None, "free": None},
        ]
        ok, order, _ = FilterRuleEngine.check_rules(meta, {"name": "Group"}, filters)
        assert ok is True
        assert order == 90  # 100 - 10


class TestFilterRuleEngineCheckTorrentFilter:
    def test_restype_filter_miss(self):
        meta = FakeMeta()
        meta.get_edtion_string = lambda: "WEB-DL"
        with patch.dict("app.conf.ModuleConf.TORRENT_SEARCH_PARAMS", {"restype": {"BluRay": "BLURAY"}}, clear=False):
            ok, _, msg = FilterRuleEngine.check_torrent_filter(
                meta, {"restype": "BluRay"}, MagicMock())
        assert ok is False
        assert "不符合质量" in msg

    def test_pix_filter_hit(self):
        meta = FakeMeta(resource_pix="1080p")
        meta.get_edtion_string = lambda: ""
        with patch.dict("app.conf.ModuleConf.TORRENT_SEARCH_PARAMS", {"pix": {"1080p": "1080P?"}}, clear=False):
            ok, _, _ = FilterRuleEngine.check_torrent_filter(
                meta, {"pix": "1080p"}, MagicMock())
        assert ok is True

    def test_team_filter_hit_with_rg_matcher(self):
        meta = FakeMeta(rev_string="Test by groupA")
        matcher = MagicMock()
        matcher.match.return_value = "groupA"
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"team": "groupA"}, matcher)
        assert ok is True
        assert meta.resource_team == "groupA"

    def test_sp_state_filter(self):
        meta = FakeMeta()
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"sp_state": "1.0 0.0"}, MagicMock(),
            uploadvolumefactor=1.0, downloadvolumefactor=0.0)
        assert ok is True

    def test_include_keyword_miss(self):
        meta = FakeMeta(rev_string="Test")
        ok, _, msg = FilterRuleEngine.check_torrent_filter(
            meta, {"include": "nomatch"}, MagicMock())
        assert ok is False
        assert "不符合包含" in msg

    def test_exclude_keyword_hit(self):
        meta = FakeMeta(rev_string="Test BAD")
        ok, _, msg = FilterRuleEngine.check_torrent_filter(
            meta, {"exclude": "bad"}, MagicMock())
        assert ok is False
        assert "不符合排除" in msg

    def test_key_filter(self):
        meta = FakeMeta(rev_string="Test Special")
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"key": "Special"}, MagicMock())
        assert ok is True


class TestFilterRuleEngineIsTorrentMatchSey:
    def test_year_match(self):
        class M:
            year = 2024
        assert FilterRuleEngine.is_torrent_match_sey(M(), None, None, "2024") is True

    def test_year_mismatch(self):
        class M:
            year = 2023
        assert FilterRuleEngine.is_torrent_match_sey(M(), None, None, "2024") is False


class TestFilterService:
    @pytest.fixture
    def svc(self):
        repo = MagicMock()
        repo.get_config_filter_group.return_value = []
        repo.get_config_filter_rule.return_value = []
        return FilterService(config_repo=repo, rg_matcher=MagicMock())

    def test_reload_calls_repo(self, svc):
        svc._config_repo.get_config_filter_group.assert_called_once()
        svc._config_repo.get_config_filter_rule.assert_called_once()

    def test_get_rule_groups_with_default(self, svc):
        svc._groups = [MagicMock(ID=1, GROUP_NAME="G1", IS_DEFAULT="Y", NOTE="")]
        assert svc.get_rule_groups(default=True) == {"id": 1, "name": "G1", "default": "Y", "note": ""}

    def test_get_rules_empty_groupid(self, svc):
        assert svc.get_rules(None) == []

    def test_check_rules_no_meta(self, svc):
        assert svc.check_rules(None) == (False, 0, "")

    def test_check_rules_skip_with_minus_one(self, svc):
        meta = FakeMeta()
        assert svc.check_rules(meta, -1) == (True, 0, "不过滤")

    def test_is_rule_free(self, svc):
        svc._groups = [MagicMock(ID=1, GROUP_NAME="G1", IS_DEFAULT="Y", NOTE="")]
        svc._rules = [MagicMock(GROUP_ID=1, PRIORITY=10, INCLUDE="", EXCLUDE="", SIZE_LIMIT="", NOTE="1.0 0.0",
                                ID=1, ROLE_NAME="R1")]
        assert svc.is_rule_free() is True

    def test_add_group_reload(self, svc):
        svc._config_repo.add_filter_group.return_value = True
        svc.add_group("NewGroup")
        svc._config_repo.add_filter_group.assert_called_once_with("NewGroup", "N")
        # reload 被调用：构造时已调用 2 次，add 后再调用 1 次
        assert svc._config_repo.get_config_filter_group.call_count == 2

    def test_check_torrent_filter_delegates(self, svc):
        meta = FakeMeta(rev_string="Test")
        ok, order, msg = svc.check_torrent_filter(meta, {})
        assert ok is True
