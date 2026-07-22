"""MessageCommandHandler 单元测试."""

from unittest.mock import MagicMock

import pytest

from app.domain.enums import SearchType
from app.services.system.message import MessageCommandHandler


class TestMessageCommandHandlerSearchCommands:
    """测试消息命令处理器对搜索/订阅类命令的路由."""

    @pytest.fixture
    def handler(self):
        search_handler = MagicMock()
        message = MagicMock()
        message.get_plugin_commands.return_value = {}
        thread_executor = MagicMock()
        return MessageCommandHandler(
            search_handler=search_handler,
            message=message,
            thread_executor=thread_executor,
        )

    @pytest.mark.parametrize(
        "msg",
        [
            "订阅 尼古猫猫",
            "搜索 尼古猫猫",
            "下载 尼古猫猫",
            "/rss 尼古猫猫",
            "/ssa 尼古猫猫",
        ],
    )
    def test_search_command_routes_to_search_handler(self, handler, msg):
        """中文订阅/搜索/下载命令及 /rss、/ssa 应路由到搜索服务."""
        handler.handle_message_job(msg, in_from=SearchType.WX, user_id="user1")

        handler._message.send_channel_msg.assert_called_once()
        call_args = handler._message.send_channel_msg.call_args
        assert "正在搜索/订阅" in call_args.kwargs.get("title", "")

        handler._thread_executor.submit.assert_called_once()
        _, args, _ = handler._thread_executor.submit.mock_calls[0]
        assert args[0] is handler._search_handler.handle
        assert args[1] == msg
        assert args[2] == SearchType.WX
        assert args[3] == "user1"

    def test_exact_command_routes_to_mapped_func(self, handler):
        """精确命令如 /sub 应执行映射函数而不是搜索."""
        subscription_monitor = MagicMock()
        handler._subscription_monitor = subscription_monitor

        handler.handle_message_job("/sub", in_from=SearchType.WX, user_id="user1")

        handler._thread_executor.submit.assert_called_once()
        _, args, _ = handler._thread_executor.submit.mock_calls[0]
        assert args[0] is subscription_monitor.run
        handler._search_handler.handle.assert_not_called()

    def test_plain_text_routes_to_search_handler(self, handler):
        """普通文本无命令前缀时也走搜索服务."""
        handler.handle_message_job("尼古猫猫", in_from=SearchType.WX, user_id="user1")

        handler._thread_executor.submit.assert_called_once()
        _, args, _ = handler._thread_executor.submit.mock_calls[0]
        assert args[0] is handler._search_handler.handle
        assert args[1] == "尼古猫猫"
