"""
队列基础设施 — 消息队列抽象接口
"""

from abc import ABC, abstractmethod
from collections.abc import Callable


class MessageQueue(ABC):
    """消息队列抽象接口"""

    @abstractmethod
    def start(self) -> None:
        """启动队列"""

    @abstractmethod
    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """停止队列"""

    @abstractmethod
    def submit(self, func: Callable, *args, name: str = "", **kwargs) -> bool:
        """提交任务到队列"""

    @abstractmethod
    def is_available(self) -> bool:
        """队列是否可用"""

    @property
    @abstractmethod
    def pending(self) -> int:
        """待处理任务数"""

    def register_handler(self, handler: Callable) -> None:
        """注册消息处理器（持久化队列消费时使用）"""
