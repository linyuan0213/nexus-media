"""事件系统单元测试."""

from unittest.mock import MagicMock

from app.events import Event, EventBus, EventHandlerRegistry, on_event
from app.events.bridge import PluginBridge
from app.events.middleware import ErrorHandlingMiddleware, MiddlewareChain


class TestEvent:
    def test_event_creation(self):
        event = Event(event_type="test.type", payload={"key": "value"})
        assert event.event_type == "test.type"
        assert event.payload == {"key": "value"}
        assert event.metadata == {}

    def test_event_with_metadata(self):
        event = Event(event_type="test.type", payload="data", metadata={"source": "test"})
        assert event.metadata == {"source": "test"}


class TestEventHandlerRegistry:
    def test_subscribe_and_get_handlers(self):
        registry = EventHandlerRegistry()
        handler1 = MagicMock()
        handler2 = MagicMock()

        registry.subscribe("test.event", handler1, priority=100)
        registry.subscribe("test.event", handler2, priority=10)

        handlers = registry.get_handlers("test.event")
        assert len(handlers) == 2
        assert handlers[0] == handler2  # priority 10 first
        assert handlers[1] == handler1  # priority 100 second

    def test_get_handlers_empty(self):
        registry = EventHandlerRegistry()
        assert registry.get_handlers("nonexistent") == []

    def test_unsubscribe(self):
        registry = EventHandlerRegistry()
        handler = MagicMock()
        registry.subscribe("test.event", handler)
        registry.unsubscribe("test.event", handler)
        assert registry.get_handlers("test.event") == []

    def test_clear(self):
        registry = EventHandlerRegistry()
        registry.subscribe("test.event", MagicMock())
        registry.clear()
        assert registry.get_handlers("test.event") == []


class TestMiddlewareChain:
    def test_middleware_chain_execution(self):
        calls = []

        from app.events.middleware import Middleware

        class TestMiddleware(Middleware):
            def process(self, event, next_handler):
                calls.append("middleware_before")
                next_handler()
                calls.append("middleware_after")

        final_handler = MagicMock()
        chain = MiddlewareChain([TestMiddleware()], final_handler)
        event = Event(event_type="test", payload=None)
        chain.execute(event)

        final_handler.assert_called_once_with(event)
        assert calls == ["middleware_before", "middleware_after"]

    def test_error_handling_middleware(self):
        calls = []

        def bad_handler(event):
            raise ValueError("test error")

        def good_handler(event):
            calls.append("good")

        chain = MiddlewareChain([ErrorHandlingMiddleware()], lambda e: bad_handler(e))
        event = Event(event_type="test", payload=None)
        chain.execute(event)  # should not raise

        # ErrorHandlingMiddleware catches exception and doesn't re-raise
        assert len(calls) == 0


class TestEventBus:
    def test_publish_with_handlers(self):
        registry = EventHandlerRegistry()
        handler = MagicMock()
        registry.subscribe("test.event", handler)

        bus = EventBus(registry=registry, bridge=PluginBridge(hook_system=MagicMock()))
        event = Event(event_type="test.event", payload={"key": "value"})
        bus.publish(event)

        handler.assert_called_once()
        called_event = handler.call_args[0][0]
        assert called_event.event_type == "test.event"
        assert called_event.payload == {"key": "value"}

    def test_publish_no_handlers(self):
        registry = EventHandlerRegistry()
        bus = EventBus(registry=registry, bridge=PluginBridge(hook_system=MagicMock()))
        event = Event(event_type="no.handlers", payload=None)
        bus.publish(event)  # should not raise

    def test_publish_async_uses_queue(self):
        registry = EventHandlerRegistry()
        mock_queue = MagicMock()

        bus = EventBus(
            registry=registry,
            bridge=PluginBridge(hook_system=MagicMock()),
            message_queue=mock_queue,
            async_event_types={"async.event"},
        )
        event = Event(event_type="async.event", payload=None)
        bus.publish(event)

        mock_queue.submit.assert_called_once()

    def test_publish_sync_not_async(self):
        registry = EventHandlerRegistry()
        handler = MagicMock()
        registry.subscribe("sync.event", handler)
        mock_queue = MagicMock()

        bus = EventBus(
            registry=registry,
            bridge=PluginBridge(hook_system=MagicMock()),
            message_queue=mock_queue,
            async_event_types={"async.event"},
        )
        event = Event(event_type="sync.event", payload=None)
        bus.publish(event)

        handler.assert_called_once()
        mock_queue.submit.assert_not_called()


class TestOnEventDecorator:
    def test_on_event_registration(self):
        from app.events.decorators import clear_subscribers, get_subscribers

        clear_subscribers()

        @on_event("test.event")
        def my_handler(event):
            pass

        subscribers = get_subscribers()
        assert len(subscribers) == 1
        assert subscribers[0][0] == "test.event"
        assert any(handler is my_handler for _, handler in subscribers[0][1])

        clear_subscribers()

    def test_auto_register(self):
        from app.events.decorators import auto_register, clear_subscribers

        clear_subscribers()

        @on_event("auto.test")
        def auto_handler(event):
            pass

        registry = EventHandlerRegistry()
        bus = EventBus(registry=registry, bridge=PluginBridge(hook_system=MagicMock()))
        auto_register(bus)

        handlers = registry.get_handlers("auto.test")
        assert len(handlers) == 1
        assert handlers[0] == auto_handler

        clear_subscribers()


class TestEventConstants:
    def test_constants_are_strings(self):
        from app.events import constants

        assert isinstance(constants.MEDIA_TRANSFER_FINISHED, str)
        assert constants.MEDIA_TRANSFER_FINISHED == "media.transfer_finished"
        assert constants.MEDIA_EPISODE_TRANSFERRED == "media.episode_transferred"
