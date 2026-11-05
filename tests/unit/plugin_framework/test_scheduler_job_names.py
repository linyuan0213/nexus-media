"""插件定时任务显示名测试."""

from unittest.mock import MagicMock

from app.plugin_framework.context import PluginContext


def test_plugin_schedule_uses_distinct_default_name():
    scheduler = MagicMock()
    ctx = PluginContext(
        "private_metadata",
        plugin_name="Private Metadata",
        scheduler_core=scheduler,
        message=MagicMock(),
    )
    ctx.schedule_cron("actress_sync", lambda: None, cron="0 3 * * *")
    assert scheduler.register_smart_cron.call_args.kwargs["name"] == "Private Metadata · actress sync"


def test_plugin_schedule_accepts_custom_name():
    scheduler = MagicMock()
    ctx = PluginContext(
        "private_metadata",
        plugin_name="Private Metadata",
        scheduler_core=scheduler,
        message=MagicMock(),
    )
    ctx.schedule_interval("browser_warmup", lambda: None, minutes=30, name="浏览器预热")
    assert scheduler.register_interval.call_args.kwargs["name"] == "浏览器预热"
