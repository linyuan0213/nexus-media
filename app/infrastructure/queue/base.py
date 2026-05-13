# -*- coding: utf-8 -*-
"""
队列基础设施 — 消息队列抽象接口
"""
from abc import ABC, abstractmethod
from typing import Callable


class MessageQueue(ABC):
    """消息队列抽象接口"""

    @abstractmethod
    def start(self) -> None:
        """启动队列"""
        pass

    @abstractmethod
    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """停止队列"""
        pass

    @abstractmethod
    def submit(self, func: Callable, *args, name: str = "", **kwargs) -> bool:
        """提交任务到队列"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """队列是否可用"""
        pass

    @property
    @abstractmethod
    def pending(self) -> int:
        """待处理任务数"""
        pass

    def register_handler(self, handler: Callable) -> None:
        """注册消息处理器（持久化队列消费时使用）"""
        pass
