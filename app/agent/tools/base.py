"""
Agent 工具层 — 仅定义工具 Schema 与参数校验

设计原则：
- 本层零依赖 Service / Message / Media 等下层模块
- 工具只负责：描述自身能力、校验 LLM 传入的参数
- 实际执行业务逻辑由上层 ToolExecutor 完成
"""

import json
from abc import ABC, abstractmethod
from typing import Any


class ToolResult:
    """工具执行结果"""

    def __init__(self, success: bool, data: Any = None, error: str = ""):
        self.success = success
        self.data = data
        self.error = error

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error}

    def to_text(self) -> str:
        if not self.success:
            return f"执行失败: {self.error}"
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, ensure_ascii=False, default=str)


class BaseTool(ABC):
    """工具基类 — 零外部依赖"""

    name: str = ""
    description: str = ""
    parameters: dict = {}

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        执行工具。
        子类可在此实现纯本地逻辑（如计算、格式化）。
        若需要调用外部服务，应通过返回 ToolResult 让上层处理。
        """

    def validate(self, kwargs: dict) -> tuple[bool, str]:
        """
        校验参数是否符合 parameters schema
        返回 (是否通过, 错误信息)
        """
        required = self.parameters.get("required", [])
        props = self.parameters.get("properties", {})
        for key in required:
            if key not in kwargs or kwargs[key] is None:
                return False, f"缺少必填参数: {key}"
        for key, value in kwargs.items():
            prop = props.get(key)
            if not prop:
                continue
            expected_type = prop.get("type")
            if expected_type == "string" and not isinstance(value, str):
                return False, f"参数 {key} 应为字符串"
            if expected_type == "integer" and not isinstance(value, int):
                return False, f"参数 {key} 应为整数"
            if expected_type == "array" and not isinstance(value, list):
                return False, f"参数 {key} 应为数组"
        return True, ""

    def to_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """工具注册表 — 纯静态，无状态"""

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool | None:
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> list[dict]:
        return [t.to_schema() for t in cls._tools.values()]

    @classmethod
    def validate_and_execute(cls, name: str, **kwargs) -> ToolResult:
        tool = cls.get(name)
        if not tool:
            return ToolResult(success=False, error=f"未知工具: {name}")
        ok, err = tool.validate(kwargs)
        if not ok:
            return ToolResult(success=False, error=err)
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
