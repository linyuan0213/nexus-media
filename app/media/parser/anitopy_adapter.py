try:
    from anitopy import anitopy as _anitopy_parse
except ImportError:
    _anitopy_parse = None

from app.media.parser.base import BaseParser, ParserResult
from app.utils.types import MediaType


class AnitopyAdapter(BaseParser):
    """anitopy 动漫解析适配器"""

    def parse(self, title: str, subtitle: str = "") -> ParserResult | None:
        if _anitopy_parse is None:
            return None
        result = _anitopy_parse(title)
        if not result:
            return None
        return ParserResult(
            title_en=result.get("anime_title"),
            title_cn=result.get("anime_title"),
            year=result.get("anime_year"),
            season=result.get("anime_season") if isinstance(result.get("anime_season"), int) else None,
            episode=result.get("episode_number") if isinstance(result.get("episode_number"), int) else None,
            resource_pix=result.get("video_resolution"),
            video_encode=result.get("video_term"),
            audio_encode=result.get("audio_term"),
            resource_team=result.get("release_group"),
            type=MediaType.ANIME,
            confidence=0.75,
        )
