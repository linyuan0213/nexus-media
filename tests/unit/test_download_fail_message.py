"""下载失败通知：标题季集与错误信息明确性测试."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.message.core.message_builder import MessageBuilder, _fail_notify_cache, _source_provider


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
        assert "❗ 原因：站点返回：相同種子當天最多下載10次" in text
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


def test_subscription_profile_is_propagated_to_item(builder, monkeypatch):
    from types import SimpleNamespace

    subscription = SimpleNamespace(
        content_profile="anime",
        image="https://img/anime.jpg",
        anchor_provider="bangumi",
        id=9,
    )
    monkeypatch.setattr(builder, "_subscription_context", lambda item: subscription)
    item = _Item(title="魔法少女", type=MediaType.TV, content_profile="default")

    enriched = builder._enrich_from_subscription(item)

    assert enriched is subscription
    assert item.content_profile == "anime"
    assert item.anchor_provider == "bangumi"
    assert item.poster_path == "https://img/anime.jpg"


def test_fail_message_inherits_anime_profile(builder, monkeypatch):
    from types import SimpleNamespace

    subscription = SimpleNamespace(
        content_profile="anime",
        image="https://img/anime.jpg",
        anchor_provider="bangumi",
        id=9,
        name="魔法少女",
    )
    monkeypatch.setattr(builder, "_subscription_context", lambda item: subscription)
    item = _Item(
        title="魔法少女",
        year="2026",
        type=MediaType.TV,
        begin_season=1,
        begin_episode=1,
        site="动漫花园",
        org_string="魔法少女 S01E01",
        enclosure="http://site/1",
        user_id=1,
        content_profile="demo",
    )

    builder.send_download_fail_message(item, "下载设置无效")

    assert item.content_profile == "anime"
    assert item.poster_path == "https://img/anime.jpg"


def test_subscription_note_backfills_poster_and_source(builder, monkeypatch):
    subscription = SimpleNamespace(
        content_profile="default",
        image="",
        anchor_provider="content_id",
        provider="aggregate",
        metadata_ref="aggregate:ABC-123",
        desc='{"poster": "https://img/abc123.jpg", "source_provider": "demo_meta"}',
        id=9,
    )
    monkeypatch.setattr(builder, "_subscription_context", lambda item: subscription)
    item = _Item(title="ABC-123", type=MediaType.MOVIE, content_profile="default")

    builder._enrich_from_subscription(item)

    assert item.poster_path == "https://img/abc123.jpg"
    assert item.provider_data["source_provider"] == "demo_meta"
    assert _source_provider(item) == "demo_meta"
