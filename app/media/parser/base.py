from typing import Optional

from pydantic import BaseModel

from app.utils.types import MediaType


class ParserResult(BaseModel):
    """文件名解析结果 — 纯数据，无外部依赖"""

    title_en: Optional[str] = None
    title_cn: Optional[str] = None
    year: Optional[str] = None
    season: Optional[int] = None
    end_season: Optional[int] = None
    episode: Optional[int] = None
    end_episode: Optional[int] = None
    resource_pix: Optional[str] = None
    video_encode: Optional[str] = None
    audio_encode: Optional[str] = None
    resource_team: Optional[str] = None
    type: Optional[MediaType] = None
    confidence: float = 0.0


class BaseParser:
    """解析器基类"""

    def parse(self, title: str, subtitle: str = "") -> Optional[ParserResult]:
        raise NotImplementedError

    def parse_batch(self, titles: list[str]) -> list[Optional[ParserResult]]:
        """默认逐条解析，子类可 override 实现 true batch"""
        return [self.parse(t) for t in titles]
