"""
动漫标题解析 — 主入口
将 MetaAnime 类拆分为纯函数模块
"""

import re

import anitopy

from app.media.models import MediaInfo
from app.media.parser.anime.name_parser import clean_name, extract_name, parse_name
from app.media.parser.anime.prepare import prepare_title
from app.media.parser.anime.resource_parser import (
    parse_customization,
    parse_encode,
    parse_resource_pix,
    parse_team,
)
from app.media.parser.anime.season_episode_parser import (
    parse_episode,
    parse_season,
    parse_type,
    parse_year,
)
from app.utils import ExceptionUtils
from app.utils.types import MediaType


def parse_anime_title(title, subtitle=None, fileflag=False) -> MediaInfo:
    """解析动漫文件名，返回 MediaInfo"""
    info = MediaInfo()
    if not title:
        return info
    info.org_string = title
    info.subtitle = subtitle
    info.fileflag = fileflag
    try:
        original_title = title
        title = re.sub(r"(\d+\.\d+)\s+", r"\1", title)
        anitopy_info_origin = anitopy.parse(title)
        title = prepare_title(title)
        anitopy_info = anitopy.parse(title)
        if anitopy_info:
            name = extract_name(info, anitopy_info, title)
            parse_name(info, name)
            clean_name(info)
            parse_year(info, anitopy_info)
            parse_season(info, anitopy_info)
            parse_episode(info, anitopy_info)
            parse_type(info, anitopy_info)
            parse_resource_pix(info, anitopy_info)
            parse_team(info, original_title, anitopy_info_origin)
            parse_customization(info, original_title)
            parse_encode(info, anitopy_info)
            info.init_subtitle(info.org_string)
            if info.subtitle:
                info.init_subtitle(info.subtitle)
        if not info.type:
            info.type = MediaType.TV
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
    return info
