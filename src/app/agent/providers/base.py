"""LLM 提供商抽象基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderConfig:
    """LLM 提供商配置"""

    name: str
    api_key: str
    api_url: str
    model: str
    proxy: str | None = None
    timeout: int = 60


class BaseProvider(ABC):
    """LLM 提供商抽象基类"""

    def __init__(self, config: ProviderConfig):
        self._config = config

    @property
    def name(self) -> str:
        return self._config.name

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        response_format: type | None = None,
    ) -> Any:
        """执行对话请求"""

    @abstractmethod
    def is_available(self) -> bool:
        """检查提供商是否可用"""

    def list_models(self) -> list[str]:
        """查询可用模型列表（可选实现）"""
        return []
