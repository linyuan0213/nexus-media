"""Message template handler — 消息模板类工具."""

from typing import Any

from app.agent.tools.base import ToolResult
from app.message.templates import DEFAULT_MESSAGE_TEMPLATES
from app.utils.json_utils import JsonUtils


def message_template(
    deps: dict[str, Any],
    action: str,
    msg_type: str = "",
    title: str = "",
    text: str = "",
    client_id: int = 0,
    **_,
) -> ToolResult:
    if action == "list":
        types = list(DEFAULT_MESSAGE_TEMPLATES.keys())
        return ToolResult(success=True, data={"types": types})

    if action == "get":
        if not msg_type:
            return ToolResult(success=False, error="请指定消息类型 msg_type")
        default = DEFAULT_MESSAGE_TEMPLATES.get(msg_type)
        if not default:
            return ToolResult(success=False, error=f"未知消息类型: {msg_type}")
        custom = None
        if client_id:
            clients = deps["message"].get_message_client_info()
            for c in clients:
                if c.get("id") == client_id:
                    custom = c.get("templates", {}).get(msg_type)
                    break
        return ToolResult(success=True, data={"msg_type": msg_type, "default": default, "custom": custom})

    if action == "update":
        if not msg_type or not title or not text:
            return ToolResult(success=False, error="update 需要 msg_type, title, text 参数")
        clients = deps["message"].get_message_client_info()
        target = next((c for c in clients if (client_id == 0 or c.get("id") == client_id)), None)
        if not target:
            return ToolResult(success=False, error="未找到目标客户端")
        templates = target.get("templates", {}) or {}
        templates[msg_type] = {"title": title, "text": text}
        deps["message_client_service"].upsert_client(
            name=target.get("name"),
            cid=target.get("id"),
            ctype=target.get("type"),
            config=JsonUtils.dumps(target.get("config", {})),
            switches=target.get("switches", []),
            interactive=1 if target.get("interactive") else 0,
            enabled=1 if target.get("enabled") else 0,
            templates=JsonUtils.dumps(templates),
        )
        return ToolResult(success=True, data=f"模板 {msg_type} 已更新")

    return ToolResult(success=False, error=f"未知操作: {action}")
