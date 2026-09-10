"""订阅 fan-out 进度联动与管理员失败通知测试（ADR-021 5.4/5.6）."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.message.core.message_builder import MessageBuilder
from app.services.subscribe.management.finish_service import SubscribeFinishService
from app.services.subscribe.management.service import SubscribeService
from app.services.subscribe.management.utils import tv_filter_signature


def _tv_row(rid, tmdb="100", season="S01", pix="", over_edition=False, user_id=1):
    return SimpleNamespace(
        id=rid,
        tmdb_id=tmdb,
        season=season,
        over_edition=over_edition,
        user_id=user_id,
        filter_restype="",
        filter_pix=pix,
        filter_team="",
        filter_rule=0,
        filter_include="",
        filter_exclude="",
        filter_free=False,
    )


def _media():
    m = MagicMock()
    m.tmdb_id = "100"
    m.get_season_string.return_value = "S01"
    m.get_season_seq.return_value = "1"
    m.get_title_string.return_value = "测试剧"
    return m


class TestTvLackSiblingSync:
    def setup_method(self):
        self.svc = object.__new__(SubscribeService)
        self.svc._tv_repo = MagicMock()

    def test_lack_updates_siblings_with_same_filter(self):
        primary = _tv_row(1)
        sibling = _tv_row(2, user_id=2)
        other_quality = _tv_row(3, pix="4k", user_id=3)
        self.svc._tv_repo.get_all.side_effect = lambda *a, **k: (
            [primary] if k.get("rssid") else [primary, sibling, other_quality]
        )
        seasoninfo = [{"season": "1", "episodes": [1, 2]}]
        self.svc.update_subscribe_tv_lack(1, _media(), seasoninfo)
        # 主订阅 + 同要求兄弟均更新缺集；质量不同者跳过
        updated = [c.kwargs.get("rssid") for c in self.svc._tv_repo.update_lack.call_args_list]
        assert updated == [1, 2]

    def test_over_edition_sibling_not_synced(self):
        primary = _tv_row(1)
        sibling = _tv_row(2, user_id=2, over_edition=True)
        self.svc._tv_repo.get_all.side_effect = lambda *a, **k: [primary] if k.get("rssid") else [primary, sibling]
        self.svc.update_subscribe_tv_lack(1, _media(), [{"season": "1", "episodes": [1]}])
        updated = [c.kwargs.get("rssid") for c in self.svc._tv_repo.update_lack.call_args_list]
        assert updated == [1]


class TestTvFinishSiblingFanout:
    def test_finish_deletes_qualifying_siblings(self):
        svc = object.__new__(SubscribeFinishService)
        primary = _tv_row(1)
        sibling = _tv_row(2, user_id=2)
        different = _tv_row(3, pix="4k", user_id=3)
        svc._tv_repo = MagicMock()
        svc._tv_repo.get_all.return_value = [primary, sibling, different]
        deleted = []
        svc._finish_sibling_tvs(primary, _media(), lambda mtype, rssid: deleted.append(rssid))
        assert deleted == [2]


class TestAdminFailureNotification:
    def _builder(self):
        return MessageBuilder(MagicMock(), MagicMock(), MagicMock())

    def test_targets_superadmins(self):
        b = self._builder()
        with patch("app.message.core.message_builder.RBACUserRepositoryAdapter") as adapter:
            adapter.return_value.get_user_ids_by_role_code.return_value = [1, 2]
            b._send_admin_msg("标题", "内容", url="unidentification")
        assert b._dispatcher.send_user_msg.call_count == 2
        roles = [c.args[0] for c in b._dispatcher.send_user_msg.call_args_list]
        assert roles == [1, 2]
        b._messagecenter.insert_system_message.assert_not_called()

    def test_fallback_global_when_no_admin(self):
        b = self._builder()
        with patch("app.message.core.message_builder.RBACUserRepositoryAdapter") as adapter:
            adapter.return_value.get_user_ids_by_role_code.return_value = []
            b._send_admin_msg("标题", "内容")
        b._messagecenter.insert_system_message.assert_called_once()


class TestFilterSignature:
    def test_entity_and_model_field_names_compatible(self):
        entity = _tv_row(1)
        model = SimpleNamespace(
            FILTER_RESTYPE="",
            FILTER_PIX="",
            FILTER_TEAM="",
            FILTER_RULE=0,
            FILTER_INCLUDE="",
            FILTER_EXCLUDE="",
            FILTER_FREE=False,
        )
        assert tv_filter_signature(entity) == tv_filter_signature(model)
