"""默认消息模板渲染测试（防止 Jinja 语法回归）."""

import pytest

from app.domain.media_types import ProviderMediaType
from app.media.models import MediaInfo
from app.message.core.template_engine import TemplateEngine


class _Item(MediaInfo):
    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def engine():
    return TemplateEngine()


def _item():
    return _Item(
        title="少女怪兽焦糖味",
        year="2026",
        type=ProviderMediaType.SERIES,
        begin_season=1,
        begin_episode=3,
        end_episode=3,
        site="M-Team",
        org_string="Otome Kaijuu Caramelise S01E03 1080p",
        seeders=12,
        size=1234567890,
        hit_and_run=False,
        enclosure="http://site/dlv2?sign=secret-token",
    )


def test_download_fail_template_renders_and_hides_link(engine):
    title, text = engine.apply_client_template(
        {}, "download_fail", {"item": _item(), "error_msg": "站点返回：相同種子當天最多下載10次"}
    )
    assert title and "S01" in title and "E03" in title
    assert "添加下载失败" in title
    assert "原因：站点返回：相同種子當天最多下載10次" in text
    # 默认全局模板不得暴露签名下载链接
    assert "sign=secret-token" not in text
    assert "enclosure" not in text


def test_download_start_template_renders(engine):
    title, text = engine.apply_client_template({}, "download_start", {"item": _item()})
    assert title and "开始下载" in title
    assert "站点" in text and "做种" in text


def test_transfer_finished_template_renders(engine):
    item = _item()
    title, text = engine.apply_client_template(
        {},
        "transfer_finished",
        {
            "media_info": item,
            "total_episodes": 12,
            "exist_filenum": 0,
            "category_flag": False,
            "in_from": "RSS",
        },
    )
    assert title and "已入库" in title and "共12集" in title
    assert "类型" in text


def test_rss_added_and_finished_templates_render(engine):
    item = _item()
    item.user_name = "linyuan"
    added_title, added_text = engine.apply_client_template({}, "rss_added", {"media_info": item, "in_from": "WEB"})
    assert added_title and "已添加订阅" in added_title
    assert "用户：linyuan" in added_text

    finished_title, finished_text = engine.apply_client_template({}, "rss_finished", {"media_info": item})
    assert finished_title and "已完成订阅" in finished_title
    assert "类型" in finished_text


def test_transfer_fail_template_renders(engine):
    title, text = engine.apply_client_template(
        {}, "transfer_fail", {"count": 2, "path": "/downloads/x", "text": "磁盘空间不足"}
    )
    assert title and "入库失败" in title
    assert "原因：磁盘空间不足" in text


def test_plugin_profile_template_override_and_fallback(engine):
    from app.message.template_registry import message_template_registry

    plugin_id = "test_message_templates"
    message_template_registry.register_pack(
        plugin_id,
        {
            "custom": {
                "rss_added": {
                    "title": "CUSTOM 已添加：{{ media_info.get_title_string() }}",
                    "text": "类型：{{ profile_label }}",
                }
            }
        },
        {"custom": "CUSTOM"},
    )
    try:
        title, text = engine.apply_client_template(
            {},
            "rss_added",
            {"media_info": _item(), "in_from": "WEB"},
            content_profile="custom",
        )
        assert "CUSTOM 已添加：少女怪兽焦糖味" in title
        assert text == "类型：CUSTOM"
        profiles = message_template_registry.list_profiles()
        assert any(p["key"] == "custom" and p["label"] == "CUSTOM" for p in profiles)
    finally:
        message_template_registry.unregister_plugin(plugin_id)

    default_title, _ = engine.apply_client_template(
        {},
        "rss_added",
        {"media_info": _item(), "in_from": "WEB"},
        content_profile="custom",
    )
    assert "已添加订阅" in default_title


def test_system_message_uses_plugin_template_by_content_profile(engine):
    """Web 系统消息与外部渠道共用模板选择，插件画像不得回退到核心模板."""
    from unittest.mock import MagicMock

    from app.message.core.message_builder import MessageBuilder
    from app.message.template_registry import message_template_registry

    plugin_id = "test_web_system_template"
    message_template_registry.register_pack(
        plugin_id,
        {
            "custom": {
                "transfer_finished": {
                    "title": "CUSTOM 入库：{{ media_info.title }}",
                    "text": "来源：{{ source_provider }}",
                }
            }
        },
        {"custom": "CUSTOM"},
    )
    try:
        builder = MessageBuilder(MagicMock(), MagicMock(), MagicMock(), template_engine=engine)
        title, text = builder._render_system_message(
            "transfer_finished",
            {"media_info": _item(), "content_profile": "custom", "source_provider": "Demo"},
            "core title",
            "core text",
        )
        assert title == "CUSTOM 入库：少女怪兽焦糖味"
        assert text == "来源：Demo"
    finally:
        message_template_registry.unregister_plugin(plugin_id)


def test_system_message_falls_back_to_core_when_profile_missing(engine):
    from unittest.mock import MagicMock

    from app.message.core.message_builder import MessageBuilder

    builder = MessageBuilder(MagicMock(), MagicMock(), MagicMock(), template_engine=engine)
    title, text = builder._render_system_message(
        "transfer_finished",
        {"media_info": _item(), "content_profile": "", "in_from": "RSS"},
        "core title",
        "core text",
    )
    assert title and title != "core title"
    assert "已入库" in title
    assert text


def test_rss_finished_default_movie_notifies_owner(engine):
    """普通电影完成订阅同样要发通知，并定向到 owner 使用画像模板."""
    from unittest.mock import MagicMock, patch

    from app.message.core.message_builder import MessageBuilder

    item = _Item(
        title="普通电影",
        year="2026",
        type=ProviderMediaType.MOVIE,
        content_profile="default",
        user_id=7,
    )
    dispatcher = MagicMock()
    builder = MessageBuilder(MagicMock(), dispatcher, MagicMock(), template_engine=engine)
    with patch("app.message.core.message_builder.resolve_subscription_context", return_value=None):
        builder.send_rss_finished_message(item, owner_user_id=7)

    dispatcher.send_user_msg.assert_called_once()
    kwargs = dispatcher.send_user_msg.call_args.kwargs
    assert kwargs["msg_type"] == "rss_finished"
    assert kwargs["variables"]["content_profile"] == "default"


def test_plugin_profile_template_precedes_client_generic_template():
    from app.message.core.template_engine import TemplateEngine
    from app.message.template_registry import message_template_registry

    message_template_registry.register_pack(
        "test-profile-priority",
        {"pluginpriority": {"rss_finished": {"title": "PLUGIN {{ profile_label }}", "text": "plugin body"}}},
        labels={"pluginpriority": "CUSTOM"},
    )
    try:
        title, text = TemplateEngine().apply_client_template(
            {"name": "wechat", "templates": {"rss_finished": {"title": "CORE", "text": "core body"}}},
            "rss_finished",
            {"content_profile": "pluginpriority"},
            content_profile="pluginpriority",
        )
        assert title == "PLUGIN CUSTOM"
        assert text == "plugin body"
    finally:
        message_template_registry.unregister_plugin("test-profile-priority")
