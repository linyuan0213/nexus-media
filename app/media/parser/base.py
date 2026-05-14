from pydantic import BaseModel

from app.utils.types import MediaType


class ParserResult(BaseModel):
    """文件名解析结果 — 纯数据，无外部依赖"""

    title_en: str | None = None
    title_cn: str | None = None
    year: str | None = None
    season: int | None = None
    end_season: int | None = None
    episode: int | None = None
    end_episode: int | None = None
    resource_pix: str | None = None
    video_encode: str | None = None
    audio_encode: str | None = None
    resource_team: str | None = None
    type: MediaType | None = None
    confidence: float = 0.0


class BaseParser:
    """解析器基类"""

    def parse(self, title: str, subtitle: str = "") -> ParserResult | None:
        raise NotImplementedError

    def parse_batch(self, titles: list[str]) -> list[ParserResult | None]:
        """默认逐条解析，子类可 override 实现 true batch"""
        return [self.parse(t) for t in titles]
