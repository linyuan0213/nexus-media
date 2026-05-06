import os.path
import regex as re
from typing import Optional

import log
from app.helper import WordsHelper
from app.media.meta.metaanime import MetaAnime
from app.media.meta.metavideo import MetaVideo
from app.utils.types import MediaType
from app.core.constants import RMT_MEDIAEXT


def MetaInfo(title: str, subtitle: Optional[str] = None, mtype: Optional[MediaType] = None):
    """
    媒体信息工厂函数，根据名称自动识别类型（动漫/影视）

    Args:
        title: 标题、种子名、文件名
        subtitle: 副标题、描述
        mtype: 指定识别类型，为空则自动识别

    Returns:
        MetaAnime 或 MetaVideo 实例
    """
    org_title = title
    rev_title, msg, used_info = WordsHelper().process(title)
    if subtitle:
        subtitle, _, _ = WordsHelper().process(subtitle)

    if msg:
        for msg_item in msg:
            log.warn("【Meta】%s" % msg_item)

    fileflag = bool(org_title and os.path.splitext(org_title)[-1] in RMT_MEDIAEXT)

    if mtype == MediaType.ANIME or _is_anime(rev_title):
        meta_info = MetaAnime(rev_title, subtitle, fileflag)
    else:
        meta_info = MetaVideo(rev_title, subtitle, fileflag)

    meta_info.org_string = org_title
    meta_info.rev_string = rev_title
    meta_info.ignored_words = used_info.get("ignored")
    meta_info.replaced_words = used_info.get("replaced")
    meta_info.offset_words = used_info.get("offset")

    return meta_info


def _is_anime(name: str) -> bool:
    """判断名称是否属于动漫"""
    if not name:
        return False
    if re.search(r'【[+0-9XVPI-]+】\s*【', name, re.IGNORECASE):
        return True
    if re.search(r'\s+-\s+[\dv]{1,4}\s+', name, re.IGNORECASE):
        return True
    if re.search(r"S\d{2}\s*-\s*S\d{2}|S\d{2}|\s+S\d{1,2}|EP?\d{2,4}\s*-\s*EP?\d{2,4}|EP?\d{2,4}|\s+EP?\d{1,4}", name,
                  re.IGNORECASE):
        return False
    if re.search(r'\[[+0-9XVPI-]+]\s*\[', name, re.IGNORECASE):
        return True
    return False
