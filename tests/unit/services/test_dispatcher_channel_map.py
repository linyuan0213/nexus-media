"""渠道名 → 交互客户端 key 解析测试."""

from unittest.mock import MagicMock, patch

import pytest

from app.message.core.dispatcher import MessageDispatcher


@pytest.mark.parametrize(
    ("channel", "expected"),
    [
        ("微信", "WX"),
        ("wechat", "WX"),
        ("WeChat", "WX"),
        ("weixin", "WX"),
        ("WX", "WX"),
        ("飞书", "FEISHU"),
        ("feishu", "FEISHU"),
        ("Lark", "FEISHU"),
        ("钉钉", "DINGTALK"),
        ("dingtalk", "DINGTALK"),
        ("电报", "TG"),
        ("TG", "TG"),
        ("群晖", "SYNOLOGY"),
        ("slack", "SLACK"),
    ],
)
def test_resolve_channel_key_aliases(channel, expected):
    assert MessageDispatcher._resolve_channel_key(channel) == expected


@pytest.mark.parametrize("channel", [None, "", "  ", "unknown_channel"])
def test_resolve_channel_key_unknown(channel):
    assert MessageDispatcher._resolve_channel_key(channel) is None


def test_send_user_msg_routes_chinese_channel_with_template():
    """中文渠道名「微信」应解析为 WX 并按模板发送（含 msg_type/variables）."""
    dispatcher = MessageDispatcher(client_manager=MagicMock(), messagecenter=MagicMock())
    binding_service = MagicMock()
    binding_service.list_bindings.return_value = [{"channel": "微信", "channel_user_id": "LinYuan"}]
    dispatcher.set_channel_binding_service(binding_service)
    dispatcher._client_manager.get_interactive_client.return_value = {"client": MagicMock(), "name": "微信"}
    template_engine = MagicMock()
    template_engine.apply_client_template.return_value = ("title", "text")

    with patch.object(dispatcher, "sendmsg", return_value=True) as mock_sendmsg:
        delivered = dispatcher.send_user_msg(
            1,
            "t",
            "x",
            msg_type="download_start",
            variables={"a": 1},
            template_engine=template_engine,
        )

    assert delivered is True
    dispatcher._client_manager.get_interactive_client.assert_called_with("WX")
    assert mock_sendmsg.call_args.kwargs["msg_type"] == "download_start"
    assert mock_sendmsg.call_args.kwargs["variables"] == {"a": 1}
