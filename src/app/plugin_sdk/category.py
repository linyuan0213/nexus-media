"""插件分类贡献 SDK：插件只通过本模块声明分类和规则."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CategoryContribution:
    """插件向核心注册的分类贡献.

    scope=core 时参与核心 movie/tv/anime 分类；scope=extension 时只供插件
    自身或后续扩展分类使用，不直接覆盖媒体库一级分类。
    """

    namespace: str
    media_types: tuple[str, ...]
    categories: dict[str, Any]
    fields: tuple[str, ...] = ()
    scope: str = "extension"
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.namespace.strip():
            raise ValueError("分类贡献 namespace 不能为空")
        if self.scope not in {"core", "extension"}:
            raise ValueError("分类贡献 scope 必须是 core 或 extension")
        if not self.media_types:
            raise ValueError("分类贡献 media_types 不能为空")
        if not isinstance(self.categories, dict):
            raise ValueError("分类贡献 categories 必须是字典")


@dataclass
class CategoryContributionRegistry:
    """只读的贡献列表由核心维护；此结构供类型提示/测试使用."""

    items: dict[str, CategoryContribution] = field(default_factory=dict)
