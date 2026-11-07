"""协调器事件注册回归测试."""

from unittest.mock import MagicMock

from app.di.builders import coordinators_builder
from app.events.bus import EventBus
from app.events.constants import MEDIA_EPISODE_TRANSFERRED
from app.events.decorators import clear_subscribers, get_subscribers, on_event


def test_register_subscription_handlers_flushes_pending_handlers(monkeypatch):
    clear_subscribers()
    monkeypatch.setattr(coordinators_builder, "build_rss_auto_subscribe_handler", lambda *_: None)
    monkeypatch.setattr(coordinators_builder, "build_subscribe_add_search_handler", lambda *_: None)
    monkeypatch.setattr(coordinators_builder, "build_movie_transfer_finalize_handler", lambda *_: None)
    monkeypatch.setattr(coordinators_builder, "build_transfer_fail_reopen_handler", lambda *_: None)

    def _build_episode_handler(*_):
        @on_event(MEDIA_EPISODE_TRANSFERRED)
        def _handler(event):
            pass

        return _handler

    monkeypatch.setattr(
        coordinators_builder,
        "build_media_episode_transferred_handler",
        _build_episode_handler,
    )
    registry = MagicMock()
    event_bus = EventBus(registry=registry, bridge=MagicMock())

    try:
        coordinators_builder.register_subscription_handlers(
            event_bus=event_bus,
            subscribe_service=MagicMock(),
            queue_strategy=MagicMock(),
            thread_executor=MagicMock(),
        )

        assert registry.subscribe.call_count == 1
        assert registry.subscribe.call_args.args[0] == MEDIA_EPISODE_TRANSFERRED
        assert get_subscribers() == []
    finally:
        clear_subscribers()
