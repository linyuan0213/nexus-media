"""Event decorators 单元测试."""

from unittest.mock import MagicMock

from app.events import decorators as event_decorators


class TestOnEvent:
    def setup_method(self):
        event_decorators.clear_subscribers()

    def teardown_method(self):
        event_decorators.clear_subscribers()

    def test_on_event_with_event_bus(self):
        bus = MagicMock()

        @event_decorators.on_event("test.event", event_bus=bus)
        def handler(event):
            pass

        bus.subscribe.assert_called_once_with("test.event", handler, priority=100)
        assert event_decorators.get_subscribers() == []

    def test_on_event_without_event_bus(self):
        @event_decorators.on_event("test.event")
        def handler(event):
            pass

        subs = event_decorators.get_subscribers()
        assert len(subs) == 1
        assert subs[0][0] == "test.event"
        assert subs[0][1] == [(100, handler)]

    def test_auto_register(self):
        from app.events.bus import EventBus

        bus = MagicMock(spec=EventBus)

        @event_decorators.on_event("test.event")
        def handler(event):
            pass

        event_decorators.auto_register(bus)
        bus.subscribe.assert_called_once_with("test.event", handler, priority=100)
        assert event_decorators.get_subscribers() == []

    def test_auto_register_invalid_bus(self):
        @event_decorators.on_event("test.event")
        def handler(event):
            pass

        event_decorators.auto_register("not_a_bus")
        assert len(event_decorators.get_subscribers()) == 1

    def test_register_modules(self):
        event_decorators.register_modules(["os"])

    def test_register_modules_import_error(self):
        event_decorators.register_modules(["nonexistent_module_xyz"])

    def test_clear_subscribers(self):
        @event_decorators.on_event("test.event")
        def handler(event):
            pass

        event_decorators.clear_subscribers()
        assert event_decorators.get_subscribers() == []
