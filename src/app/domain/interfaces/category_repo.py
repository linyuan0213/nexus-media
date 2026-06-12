"""分类配置领域 Repository 接口"""

from typing import Protocol

from app.domain.entities.category import CategoryConfigEntity


class ICategoryConfigRepository(Protocol):
    """二级分类配置仓储接口"""

    def get_all(self) -> list[CategoryConfigEntity]:
        """获取所有分类配置"""
        ...

    def save(self, media_type: str, name: str, sort_order: int, is_default: int, rules: dict[str, str]) -> int:
        """保存分类配置，返回分类ID"""
        ...

    def delete(self, cid: int) -> None:
        """删除分类配置"""
        ...

    def clear_all(self) -> None:
        """清空所有分类配置"""
        ...
