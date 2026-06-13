from app.domain.mediatypes import MediaType
from app.media.parser._video import parse_video_title
from app.media.parser.base import BaseParser, ParserResult


class TokenAdapter(BaseParser):
    """Tokens 正则解析适配器 — 影视文件名解析"""

    def parse(self, title: str, subtitle: str = "") -> ParserResult | None:
        meta = parse_video_title(title, subtitle)
        if not meta.get_name():
            return None
        return ParserResult(
            title_cn=meta.cn_name,
            title_en=meta.en_name,
            year=meta.year,
            season=meta.begin_season,
            episode=meta.begin_episode,
            resource_pix=meta.resource_pix,
            video_encode=meta.video_encode,
            audio_encode=meta.audio_encode,
            resource_team=meta.resource_team,
            type=meta.type or MediaType.MOVIE,
            confidence=0.65,
        )
