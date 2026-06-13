"""EventBus 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.events.bus import EventBus
from app.events.types import Event


@pytest.fixture
def event_bus():
    return EventBus(
        registry=MagicMock(),
        bridge=MagicMock(),
        message_queue=MagicMock(),
        middleware=[],
        async_event_types=set(),
    )


class TestEventBus:
    def test_subscribe(self, event_bus):
        handler = MagicMock()
        event_bus.subscribe("test.event", handler)
        event_bus._registry.subscribe.assert_called_once_with("test.event", handler, 100)

    def test_publish_sync(self, event_bus):
        handler = MagicMock()
        event_bus._registry.get_handlers.return_value = [handler]
        event = Event(event_type="test.event", payload={})
        event_bus.publish(event)
        handler.assert_called_once_with(event)
        event_bus._bridge.forward.assert_called_once_with(event)

    def test_publish_async(self):
        registry = MagicMock()
        registry.get_handlers.return_value = []
        bridge = MagicMock()
        queue = MagicMock()
        bus = EventBus(
            registry=registry,
            bridge=bridge,
            message_queue=queue,
            middleware=[],
            async_event_types={"test.event"},
        )
        event = Event(event_type="test.event", payload={})
        bus.publish(event)
        queue.submit.assert_called_once()

    def test_publish_no_handlers(self, event_bus):
        event_bus._registry.get_handlers.return_value = []
        event = Event(event_type="test.event", payload={})
        event_bus.publish(event)
        event_bus._bridge.forward.assert_called_once_with(event)

    def test_shutdown(self, event_bus):
        event_bus.shutdown()
        event_bus._queue.stop.assert_called_once()

    def test_shutdown_no_queue(self):
        bus = EventBus(registry=MagicMock(), bridge=MagicMock())
        bus.shutdown()
