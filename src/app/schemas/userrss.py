from dataclasses import dataclass, field


@dataclass
class UserRssArticleListDTO:
    articles: list[dict] = field(default_factory=list)
    count: int = 0
    uses: str | None = None
    address_count: int = 0


@dataclass
class UserRssHistoryDTO:
    downloads: list[dict] = field(default_factory=list)
    count: int = 0


@dataclass
class UserRssArticleTestDTO:
    name: str | None = None
    match_flag: bool | None = None
    exist_flag: bool | None = None
    media_dict: dict | None = None


@dataclass
class UserRssTaskUpdateDTO:
    success: bool = False
