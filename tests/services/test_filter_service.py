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
        assert FilterRuleEngine.check_rules(meta, {"name": "G"}, []) == (True, 0, "G")

    def test_include_match(self):
        meta = FakeMeta(rev_string="Hello World")
        filters = [{"include": ["hello"], "pri": 1}]
        ok, order, name = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is True

    def test_include_miss(self):
        meta = FakeMeta(rev_string="Hello World")
        filters = [{"include": ["xyz"], "pri": 1}]
        ok, _, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is False

    def test_exclude_match(self):
        meta = FakeMeta(rev_string="Hello World")
        filters = [{"exclude": ["hello"], "pri": 1}]
        ok, _, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is False

    def test_size_movie_range(self):
        meta = FakeMeta(size="5GB", type=MediaType.MOVIE)
        filters = [{"size": "1,10", "pri": 1}]
        ok, _, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is True

    def test_size_movie_out_of_range(self):
        meta = FakeMeta(size="15GB", type=MediaType.MOVIE)
        filters = [{"size": "1,10", "pri": 1}]
        ok, _, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is False

    def test_free_rule_match(self):
        meta = FakeMeta(upload_volume_factor=1.0, download_volume_factor=0.0)
        filters = [{"free": "1.0 0.0", "pri": 1}]
        ok, _, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is True

    def test_free_rule_mismatch(self):
        meta = FakeMeta(upload_volume_factor=1.0, download_volume_factor=1.0)
        filters = [{"free": "1.0 0.0", "pri": 1}]
        ok, _, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert ok is False

    def test_priority_order(self):
        meta = FakeMeta(rev_string="A")
        filters = [{"include": ["a"], "pri": 10}]
        _, order, _ = FilterRuleEngine.check_rules(meta, {"name": "G"}, filters)
        assert order == 90


class TestFilterRuleEngineCheckTorrentFilter:
    def test_restype_filter_miss(self):
        meta = FakeMeta()
        meta.get_edtion_string = lambda: ""
        ok, _, msg = FilterRuleEngine.check_torrent_filter(meta, {"restype": "蓝光"}, MagicMock())
        assert ok is False
        assert "蓝光" in msg

    def test_pix_filter_hit(self):
        meta = FakeMeta(resource_pix="1080p")
        ok, _, _ = FilterRuleEngine.check_torrent_filter(meta, {"pix": "1080p"}, MagicMock())
        assert ok is True

    def test_team_filter_hit_with_rg_matcher(self):
        meta = FakeMeta(rev_string="Test by CMCT")
        rg = MagicMock()
        rg.match.return_value = "CMCT"
        ok, _, _ = FilterRuleEngine.check_torrent_filter(meta, {"team": "CMCT"}, rg)
        assert ok is True
        assert meta.resource_team == "CMCT"

    def test_sp_state_filter(self):
        meta = FakeMeta()
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"sp_state": "1.0 0.0"}, MagicMock(),
            uploadvolumefactor=1.0, downloadvolumefactor=0.0)
        assert ok is True

    def test_include_keyword_miss(self):
        meta = FakeMeta(rev_string="abc")
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"include": "xyz"}, MagicMock())
        assert ok is False

    def test_exclude_keyword_hit(self):
        meta = FakeMeta(rev_string="abc xyz")
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"exclude": "xyz"}, MagicMock())
        assert ok is False

    def test_key_filter(self):
        meta = FakeMeta(rev_string="abc")
        ok, _, _ = FilterRuleEngine.check_torrent_filter(
            meta, {"key": "abc"}, MagicMock())
        assert ok is True


class TestFilterRuleEngineIsTorrentMatchSey:
    def test_year_match(self):
        meta = MagicMock()
        meta.year = 2024
        meta.get_season_list.return_value = []
        meta.get_episode_list.return_value = []
        assert FilterRuleEngine.is_torrent_match_sey(meta, None, None, 2024) is True

    def test_year_mismatch(self):
        meta = MagicMock()
        meta.year = 2023
        meta.get_season_list.return_value = []
        meta.get_episode_list.return_value = []
        assert FilterRuleEngine.is_torrent_match_sey(meta, None, None, 2024) is False


@pytest.fixture
def svc():
    mock_group_repo = MagicMock()
    mock_group_repo.get_config_filter_group.return_value = []
    mock_rule_repo = MagicMock()
    mock_rule_repo.get_config_filter_rule.return_value = []
    mock_rg = MagicMock()
    return FilterService(filter_group_repo=mock_group_repo,
                         filter_rule_repo=mock_rule_repo,
                         rg_matcher=mock_rg)


class TestFilterService:
    def test_reload_calls_repo(self, svc):
        assert svc._filter_group_repo.get_config_filter_group.call_count >= 1

    def test_get_rule_groups_with_default(self, svc):
        svc._groups = [MagicMock(ID=1, GROUP_NAME="G1", IS_DEFAULT="Y", NOTE="")]
        result = svc.get_rule_groups(default=True)
        assert result["name"] == "G1"

    def test_get_rules_empty_groupid(self, svc):
        assert svc.get_rules("") == []

    def test_check_rules_no_meta(self, svc):
        assert svc.check_rules(None) == (False, 0, "")

    def test_check_rules_skip_with_minus_one(self, svc):
        meta = MagicMock()
        assert svc.check_rules(meta, -1) == (True, 0, "不过滤")

    def test_is_rule_free(self, svc):
        svc._groups = [MagicMock(ID=1, GROUP_NAME="G", IS_DEFAULT="Y", NOTE="")]
        svc._rules = [MagicMock(GROUP_ID=1, ID=1, ROLE_NAME="R", PRIORITY=1,
                                INCLUDE="", EXCLUDE="", SIZE_LIMIT="", NOTE="1.0 0.0")]
        assert svc.is_rule_free() is True

    def test_add_group_reload(self, svc):
        svc._filter_group_repo.add_filter_group.return_value = True
        svc.add_group("NewGroup")
        svc._filter_group_repo.add_filter_group.assert_called_once_with("NewGroup", "N")
        # reload 被调用：构造时已调用 2 次，add 后再调用 1 次
        assert svc._filter_group_repo.get_config_filter_group.call_count == 2

    def test_check_torrent_filter_delegates(self, svc):
        meta = FakeMeta(rev_string="Test")
        ok, order, msg = svc.check_torrent_filter(meta, {})
        assert ok is True


class TestImportFilterGroup:
    def test_success(self, svc):
        import base64, json
        content = base64.b64encode(json.dumps({"name": "Test", "rules": []}).encode()).decode()
        svc.add_group = MagicMock()
        svc.get_filter_groupid_by_name = MagicMock(return_value=1)
        svc.add_filter_rule = MagicMock()
        ok, msg = svc.import_filter_group(content)
        assert ok is True

    def test_invalid_format(self, svc):
        ok, msg = svc.import_filter_group("invalid")
        assert ok is False

    def test_no_name(self, svc):
        import base64, json
        content = base64.b64encode(json.dumps({}).encode()).decode()
        ok, msg = svc.import_filter_group(content)
        assert ok is False


class TestRestoreFilterGroup:
    def test_ok(self, svc):
        svc.delete_filtergroup = MagicMock()
        svc._filter_group_repo._repo = MagicMock()
        svc._filter_group_repo._repo.excute = MagicMock()
        svc.restore_filter_group(
            ["1"],
            [{"id": 1, "sql": ["SQL1"]}]
        )
        svc.delete_filtergroup.assert_called_once_with("1")
        svc._filter_group_repo._repo.excute.assert_called_once_with("SQL1")


class TestShareFilterGroup:
    def test_success(self, svc):
        svc.get_filter_group = MagicMock(return_value=[MagicMock(GROUP_NAME="G")])
        svc.get_filter_rule = MagicMock(return_value=[
            MagicMock(ROLE_NAME="R", PRIORITY=1, INCLUDE="a",
                      EXCLUDE="b", SIZE_LIMIT="", NOTE="")
        ])
        ok, msg, s = svc.share_filter_group(1)
        assert ok is True
        assert s != ""

    def test_group_not_found(self, svc):
        svc.get_filter_group = MagicMock(return_value=[])
        ok, msg, s = svc.share_filter_group(1)
        assert ok is False
        assert "规则组不存在" in msg

    def test_no_rules(self, svc):
        svc.get_filter_group = MagicMock(return_value=[MagicMock(GROUP_NAME="G")])
        svc.get_filter_rule = MagicMock(return_value=[])
        ok, msg, s = svc.share_filter_group(1)
        assert ok is False
        assert "没有对应规则" in msg


class TestTestRule:
    def test_match(self, svc):
        svc.check_torrent_filter = MagicMock(return_value=(True, 10, "ok"))
        flag, text, order = svc.test_rule("Title", "", "5", "1")
        assert flag is True
        assert text == "匹配"
        assert order == 90

    def test_no_match(self, svc):
        svc.check_torrent_filter = MagicMock(return_value=(False, 0, ""))
        flag, text, order = svc.test_rule("Title", "", None, None)
        assert flag is False
        assert text == "未匹配"


class TestGetRuleDetail:
    def test_with_rule(self, svc):
        svc.get_rules = MagicMock(return_value={
            "include": ["a", "b"], "exclude": ["c"]
        })
        result = svc.get_rule_detail(1, 1)
        assert result["include"] == "a\nb"
        assert result["exclude"] == "c"

    def test_empty(self, svc):
        svc.get_rules = MagicMock(return_value={})
        result = svc.get_rule_detail(1, 1)
        assert result == {}
