"""事件注册机制单元测试."""

from unittest.mock import patch

from app.events.decorators import register_modules


class TestRegisterModules:
    """Test suite for register_modules."""

    def test_register_modules_success(self):
        """测试成功导入模块."""
        with patch("app.events.decorators.importlib.import_module") as mock_import:
            modules = ["app.services.test1.handlers", "app.services.test2.handlers"]
            register_modules(modules)

            assert mock_import.call_count == 2
            mock_import.assert_any_call("app.services.test1.handlers")
            mock_import.assert_any_call("app.services.test2.handlers")

    def test_register_modules_import_error(self):
        """测试导入失败时跳过."""
        with patch("app.events.decorators.importlib.import_module") as mock_import:
            mock_import.side_effect = [None, ImportError("No module")]

            modules = ["app.services.ok.handlers", "app.services.missing.handlers"]
            # Should not raise
            register_modules(modules)

            assert mock_import.call_count == 2

    def test_register_modules_empty(self):
        """测试空列表."""
        with patch("app.events.decorators.importlib.import_module") as mock_import:
            register_modules([])
            mock_import.assert_not_called()

    def test_register_modules_triggers_on_event(self):
        """测试导入后触发 @on_event 注册."""
        from app.events.decorators import clear_subscribers, get_subscribers

        clear_subscribers()

        # Simulate a module with @on_event by directly registering
        from app.events import on_event

        @on_event("register.test")
        def _test_handler(event):
            pass

        subscribers = get_subscribers()
        assert len(subscribers) == 1
        assert subscribers[0][0] == "register.test"

        clear_subscribers()
