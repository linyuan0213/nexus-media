"""下载失败通知：标题季集与错误信息明确性测试."""

from unittest.mock import MagicMock

import pytest

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.message.core.message_builder import MessageBuilder, _fail_notify_cache


class _Item(MediaInfo):
    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture(autouse=True)
def clear_fail_cache():
    _fail_notify_cache.clear()
    yield
    _fail_notify_cache.clear()


@pytest.fixture
def builder():
    b = MessageBuilder(client_manager=MagicMock(), dispatcher=MagicMock(), messagecenter=MagicMock())
    b._client_manager.active_clients = []
    return b


class TestDownloadFailMessage:
    def test_title_contains_season_and_episode(self, builder):
        item = _Item(
            title="少女怪兽焦糖味",
            year="2026",
            type=MediaType.TV,
            begin_season=1,
            begin_episode=3,
            end_episode=3,
            site="M-Team",
            org_string="Otome S01E03",
            enclosure="http://site/dlv2?sign=a",
            user_id=1,
        )
        builder.send_download_fail_message(item, "站点返回：相同種子當天最多下載10次")

        owner_id, title, text = builder._dispatcher.send_user_msg.call_args.args[:3]
        assert owner_id == 1
        assert "少女怪兽焦糖味" in title
        assert "S01" in title and "E03" in title
        assert "错误信息：站点返回：相同種子當天最多下載10次" in text
        assert "M-Team" in text

    def test_season_pack_title_keeps_season_only(self, builder):
        item = _Item(
            title="某剧",
            year="2026",
            type=MediaType.TV,
            begin_season=1,
            site="观众",
            org_string="某剧 S01 全12集",
            enclosure="http://site/dlv2?sign=b",
            user_id=1,
        )
        builder.send_download_fail_message(item, "下载种子文件出现异常：HTTP 404")

        _, title, text = builder._dispatcher.send_user_msg.call_args.args[:3]
        assert "S01" in title
        assert "HTTP 404" in text

    def test_fail_message_deduplicated_same_enclosure(self, builder):
        item = _Item(
            title="某剧",
            year="2026",
            type=MediaType.TV,
            begin_season=1,
            begin_episode=5,
            end_episode=5,
            site="观众",
            org_string="某剧 S01E05",
            enclosure="http://site/dlv2?sign=dup",
            user_id=1,
        )
        builder.send_download_fail_message(item, "第一次失败")
        builder.send_download_fail_message(item, "第二次失败")

        assert builder._dispatcher.send_user_msg.call_count == 1
