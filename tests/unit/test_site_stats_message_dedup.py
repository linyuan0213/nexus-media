"""站点数据统计消息去重测试.

背景：统计消息标题经消息模板渲染后带 emoji 前缀（如「📊 站点数据统计」），
历史实现用标题全等匹配导致去重永久失效，每轮刷新都会重复发送统计消息。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.sites.site_userinfo import SiteUserInfo


def _make_userinfo(message: MagicMock) -> SiteUserInfo:
    """构造只注入 message 的 SiteUserInfo（跳过构造函数中的重依赖）."""
    userinfo = SiteUserInfo.__new__(SiteUserInfo)
    userinfo.message = message
    return userinfo


def _message_with_history(items: list[dict]) -> MagicMock:
    message = MagicMock()
    message.recent_web_messages.return_value = items
    return message


class TestStatsMessageUnchanged:
    """标题匹配需兼容模板渲染后的 emoji 前缀与自定义模板."""

    def test_matches_title_with_emoji_prefix(self):
        """模板默认渲染为「📊 站点数据统计」，内容一致时应判定为未变化."""
        body = "共 3 个站点  ⬆️ 1.0M  ⬇️ 2.0M\n\n1. 观众  ⬆️ 1.0M  ⬇️ -"
        message = _message_with_history([{"title": "📊 站点数据统计", "content": body}])

        assert _make_userinfo(message)._stats_message_unchanged(body) is True

    def test_matches_title_without_emoji(self):
        """客户端自定义模板去掉 emoji 时同样应命中，避免依赖展示文案."""
        body = "共 1 个站点  ⬆️ 1.0M"
        message = _message_with_history([{"title": "站点数据统计", "content": body}])

        assert _make_userinfo(message)._stats_message_unchanged(body) is True

    def test_matches_custom_title_variant(self):
        """自定义模板可改写标题，只要含标识词即视为同一类消息."""
        body = "共 1 个站点  ⬆️ 1.0M"
        message = _message_with_history([{"title": "【站点数据统计】日报", "content": body}])

        assert _make_userinfo(message)._stats_message_unchanged(body) is True

    def test_returns_false_when_content_differs(self):
        """标题命中但内容不同 → 判定为有变化，需要发送."""
        message = _message_with_history([{"title": "📊 站点数据统计", "content": "共 2 个站点  ⬆️ 9.9M"}])

        assert _make_userinfo(message)._stats_message_unchanged("共 2 个站点  ⬆️ 1.0M") is False

    def test_ignores_unrelated_titles(self):
        """非统计类消息不应参与去重判断."""
        message = _message_with_history(
            [
                {"title": "✅ 凡人修仙传 (2020) S01 E199 已入库", "content": "共 1 个站点  ⬆️ 1.0M"},
                {"title": "🔌 [自动签到任务完成]", "content": "共 1 个站点  ⬆️ 1.0M"},
            ]
        )

        assert _make_userinfo(message)._stats_message_unchanged("共 1 个站点  ⬆️ 1.0M") is False

    def test_uses_latest_matching_message(self):
        """存在多条统计消息时，应与最近一条（列表末尾）比较."""
        latest = "共 1 个站点  ⬆️ 2.0M"
        message = _message_with_history(
            [
                {"title": "📊 站点数据统计", "content": "共 1 个站点  ⬆️ 1.0M"},
                {"title": "🔌 [其它任务]", "content": "x"},
                {"title": "📊 站点数据统计", "content": latest},
            ]
        )

        assert _make_userinfo(message)._stats_message_unchanged(latest) is True
        assert _make_userinfo(message)._stats_message_unchanged("共 1 个站点  ⬆️ 1.0M") is False

    def test_no_history_returns_false(self):
        message = _message_with_history([])

        assert _make_userinfo(message)._stats_message_unchanged("任意内容") is False

    def test_message_missing_returns_false(self):
        """message 未注入时不抛异常，按“有变化”处理."""
        userinfo = SiteUserInfo.__new__(SiteUserInfo)
        userinfo.message = None

        assert userinfo._stats_message_unchanged("任意内容") is False

    def test_history_exception_is_swallowed(self):
        """查询历史异常时降级为“有变化”，不影响刷新主流程."""
        message = MagicMock()
        message.recent_web_messages.side_effect = RuntimeError("db down")

        assert _make_userinfo(message)._stats_message_unchanged("任意内容") is False

    @pytest.mark.parametrize(
        "title",
        [
            "📊 站点数据统计",
            "站点数据统计",
            "【站点数据统计】",
            "  📊 站点数据统计  ",
        ],
    )
    def test_title_variants_all_match(self, title):
        """各类标题变体都应被识别为统计消息（回归：曾因全等匹配全部失配）."""
        body = "共 1 个站点  ⬆️ 1.0M"
        message = _message_with_history([{"title": title, "content": body}])

        assert _make_userinfo(message)._stats_message_unchanged(body) is True
