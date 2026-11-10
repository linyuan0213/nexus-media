"""站点数据统计消息去重测试（按稳定消息类型匹配）."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.sites.site_userinfo import SiteUserInfo

STATS_TYPE = "ptrefresh_date_message"


def _make_userinfo(message: MagicMock) -> SiteUserInfo:
    userinfo = SiteUserInfo.__new__(SiteUserInfo)
    userinfo.message = message
    return userinfo


def _message_with_history(items: list[dict]) -> MagicMock:
    message = MagicMock()
    message.recent_web_messages.return_value = items
    return message


def test_matches_by_message_type_regardless_of_title():
    body = "共 3 个站点  ⬆️ 1.0M  ⬇️ 2.0M\n\n1. 观众  ⬆️ 1.0M  ⬇️ -"
    message = _message_with_history([{"msg_type": STATS_TYPE, "title": "📊 任意标题", "content": body}])

    assert _make_userinfo(message)._stats_message_unchanged(body) is True


def test_returns_false_when_content_differs():
    message = _message_with_history(
        [{"msg_type": STATS_TYPE, "title": "📊 站点数据统计", "content": "共 2 个站点  ⬆️ 9.9M"}]
    )

    assert _make_userinfo(message)._stats_message_unchanged("共 2 个站点  ⬆️ 1.0M") is False


def test_ignores_same_title_with_different_type():
    message = _message_with_history(
        [{"msg_type": "download_start", "title": "📊 站点数据统计", "content": "共 1 个站点"}]
    )

    assert _make_userinfo(message)._stats_message_unchanged("共 1 个站点") is False


def test_legacy_message_without_type_is_not_used():
    message = _message_with_history([{"title": "📊 站点数据统计", "content": "共 1 个站点"}])

    assert _make_userinfo(message)._stats_message_unchanged("共 1 个站点") is False


def test_uses_latest_matching_message_type():
    latest = "共 1 个站点  ⬆️ 2.0M"
    message = _message_with_history(
        [
            {"msg_type": STATS_TYPE, "title": "旧", "content": "共 1 个站点  ⬆️ 1.0M"},
            {"msg_type": "download_start", "title": "其它", "content": "x"},
            {"msg_type": STATS_TYPE, "title": "新", "content": latest},
        ]
    )

    assert _make_userinfo(message)._stats_message_unchanged(latest) is True
    assert _make_userinfo(message)._stats_message_unchanged("共 1 个站点  ⬆️ 1.0M") is False


def test_no_history_returns_false():
    assert _make_userinfo(_message_with_history([]))._stats_message_unchanged("任意内容") is False


def test_message_missing_returns_false():
    userinfo = SiteUserInfo.__new__(SiteUserInfo)
    userinfo.message = None

    assert userinfo._stats_message_unchanged("任意内容") is False


def test_history_exception_is_swallowed():
    message = MagicMock()
    message.recent_web_messages.side_effect = RuntimeError("db down")

    assert _make_userinfo(message)._stats_message_unchanged("任意内容") is False
