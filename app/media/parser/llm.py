from typing import Optional

from app.agent.agents.media_recognizer import MediaRecognizer
from app.media.parser.base import BaseParser, ParserResult
from app.utils.types import MediaType


class LLMParser(BaseParser):
    """基于 LLM 的解析器 — 包装 MediaRecognizer"""

    def __init__(self):
        self._recognizer = MediaRecognizer()

    @property
    def ready(self) -> bool:
        return self._recognizer.ready

    def parse(self, title: str, subtitle: str = "") -> Optional[ParserResult]:
        result = self._recognizer.recognize(title)
        if not result:
            return None
        return self._convert(result)

    def parse_batch(self, titles: list[str]) -> list[Optional[ParserResult]]:
        results = self._recognizer.recognize_batch(titles)
        return [self._convert(r) for r in results]

    def _convert(self, result) -> Optional[ParserResult]:
        if not result:
            return None
        return ParserResult(
            title_en=result.title_en,
            title_cn=result.title_cn,
            year=str(result.year) if result.year else None,
            season=result.season,
            end_season=result.end_season,
            episode=result.episode,
            end_episode=result.end_episode,
            resource_pix=result.resolution,
            video_encode=result.video_codec,
            audio_encode=result.audio_codec,
            resource_team=result.release_group,
            type=self._map_type(result.type),
            confidence=0.9,
        )

    @staticmethod
    def _map_type(type_str: Optional[str]) -> Optional[MediaType]:
        if type_str == "anime":
            return MediaType.ANIME
        if type_str == "tv":
            return MediaType.TV
        if type_str == "movie":
            return MediaType.MOVIE
        return None
