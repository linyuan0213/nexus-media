import os.path

from app.core.constants import RMT_MEDIAEXT
from app.media.parser._anime import parse_anime_title
from app.media.parser._metainfo import _is_anime
from app.media.parser._video import parse_video_title
from app.media.parser.base import BaseParser, ParserResult


class RegexParser(BaseParser):
    """基于正则的本地解析器 — 调用纯函数 parse_video_title / parse_anime_title"""

    def parse(self, title: str, subtitle: str = "") -> ParserResult | None:
        fileflag = bool(title and os.path.splitext(title)[-1] in RMT_MEDIAEXT)
        if _is_anime(title, title):
            meta = parse_anime_title(title, subtitle, fileflag)
        else:
            meta = parse_video_title(title, subtitle, fileflag)
        if not meta.get_name():
            return None
        return ParserResult(
            title_cn=meta.cn_name,
            title_en=meta.en_name,
            year=meta.year,
            season=meta.begin_season,
            end_season=meta.end_season,
            episode=meta.begin_episode,
            end_episode=meta.end_episode,
            resource_pix=meta.resource_pix,
            resource_type=meta.resource_type,
            video_encode=meta.video_encode,
            audio_encode=meta.audio_encode,
            resource_team=meta.resource_team,
            type=meta.type,
            confidence=0.7,
            org_string=meta.org_string,
        )
