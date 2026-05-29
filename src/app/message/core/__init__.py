"""message.core package - 消息服务内部组件."""

from app.message.core.client_manager import ClientManager
from app.message.core.command_manager import CommandManager
from app.message.core.dispatcher import MessageDispatcher
from app.message.core.message_builder import MessageBuilder
from app.message.core.template_engine import TemplateEngine

__all__ = [
    "ClientManager",
    "CommandManager",
    "MessageDispatcher",
    "MessageBuilder",
    "TemplateEngine",
]
