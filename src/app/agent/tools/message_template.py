"""
消息模板工具 — 仅定义 Schema 与参数校验
实际执行由 ToolExecutor._message_template 处理
"""

from app.agent.tools.base import BaseTool, ToolRegistry


class MessageTemplateTool(BaseTool):
    """消息模板管理工具"""

    name = "message_template"
    description = "查看和修改消息通知模板，支持16种消息类型"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get", "update", "reset"],
                "description": "操作类型",
            },
            "msg_type": {
                "type": "string",
                "description": "消息类型，如 download_start, transfer_finished 等",
            },
            "title": {"type": "string", "description": "模板标题（update时使用）"},
            "text": {"type": "string", "description": "模板内容（update时使用）"},
            "client_id": {"type": "integer", "description": "客户端ID（为空则操作全局默认模板）"},
        },
        "required": ["action"],
    }

    def execute(self, **kwargs):
        # 纯本地工具：参数已在 validate 中校验
        # 实际业务逻辑由 ToolExecutor 处理
        raise NotImplementedError("message_template 应由 ToolExecutor 执行")


ToolRegistry.register(MessageTemplateTool())
