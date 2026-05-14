"""
Indexer 领域 DTO 定义
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserIndexerDTO:
    """用户已选索引器字典项"""

    id: str = ""
    name: str = ""


@dataclass
class IndexerHashDTO:
    """索引器 Hash 字典项"""

    id: str = ""
    name: str = ""
    public: bool = False
    builtin: bool = False


@dataclass
class IndexerClientInfoDTO:
    """当前索引器客户端信息"""

    client_id: str = ""
    client_type: str = ""
    client_name: str = ""


@dataclass
class IndexerResourcesResultDTO:
    """站点资源列表结果"""

    success: bool = False
    data: Any = None
    msg: str = ""


@dataclass
class IndexerSearchResultDTO:
    """索引器搜索结果包装"""

    results: list[Any] = field(default_factory=list)
    total_count: int = 0
