from dataclasses import dataclass, field


@dataclass
class WordGroupDTO:
    """自定义词组 DTO"""

    id: int = 0
    title: str = ""
    year: str = ""
    type: int = 1
    tmdbid: int = 0
    season_count: int = 0


@dataclass
class WordDTO:
    """自定义识别词 DTO"""

    id: int = 0
    replaced: str = ""
    replace: str = ""
    front: str = ""
    back: str = ""
    offset: str = ""
    type: int = 1
    group_id: int = 0
    season: int = -2
    enabled: int = 1
    regex: int = 0
    help: str = ""


@dataclass
class WordGroupExportDTO:
    """导出词组 DTO（前端展示用）"""

    id: str = ""
    name: str = ""
    link: str = ""
    type: int = 1
    seasons: str = ""
    words: dict = field(default_factory=dict)
