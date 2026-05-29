import os.path
from typing import Any

import regex as re

import log
from app.core.constants import RMT_MEDIAEXT
from app.helper import WordsHelper
from app.media.parser._anime import parse_anime_title
from app.media.parser._video import parse_video_title
from app.utils.types import MediaType


def meta_info(title: str, subtitle: str | None = None, mtype: MediaType | None = None) -> Any:
    """
    媒体信息工厂函数，根据名称自动识别类型（动漫/影视）

    纯本地正则解析，不调用外部 LLM。
    LLM Agent 识别在 MediaService.identify() / identify_batch() 中使用。

    Args:
        title: 标题、种子名、文件名
        subtitle: 副标题、描述
        mtype: 指定识别类型，为空则自动识别

    Returns:
        MediaInfo 实例
    """
    org_title = title
    rev_title, msg, used_info = WordsHelper().process(title)
    if subtitle:
        subtitle, _, _ = WordsHelper().process(subtitle)

    if msg:
        for msg_item in msg:
            log.warn(f"【Meta】{msg_item}")

    fileflag = bool(org_title and os.path.splitext(org_title)[-1] in RMT_MEDIAEXT)

    if mtype == MediaType.ANIME or _is_anime(rev_title, org_title):
        media_info = parse_anime_title(rev_title, subtitle, fileflag)
    else:
        media_info = parse_video_title(rev_title, subtitle, fileflag)

    media_info.org_string = org_title
    media_info.rev_string = rev_title
    media_info.ignored_words = used_info.get("ignored")
    media_info.replaced_words = used_info.get("replaced")
    media_info.offset_words = used_info.get("offset")

    # 排除 FPS/Hz 参数被误判为集数（如 120FPS → E120）
    if media_info.begin_episode and org_title:
        if re.search(rf"{media_info.begin_episode}\s*(FPS|HZ)", org_title, re.IGNORECASE):
            media_info.begin_episode = None
            media_info.end_episode = None
            media_info.total_episodes = 0

    return media_info


def _is_anime(rev_name: str, org_name: str) -> bool:
    """判断名称是否属于动漫"""
    # 先移除 CRC32/哈希值标记，避免干扰判断
    rev_name = re.sub(r"\[[0-9A-F]{8}\]", "", rev_name, flags=re.IGNORECASE)
    org_name = re.sub(r"\[[0-9A-F]{8}\]", "", org_name, flags=re.IGNORECASE)

    # 排除成人视频（SEX 后可能直接跟数字如 SEX153，不能用 \b）
    for name in (rev_name, org_name):
        if name and re.search(r"(?:SEX|HENTAI|AV\b|無码|R18|成人)", name, re.IGNORECASE):
            return False
    if not rev_name:
        return False
    # 匹配中文方括号标记：要求至少包含一个非数字字符（如 720P、X264、V2），排除纯数字如 【12】
    if re.search(r"【(?:[+XVPI-]+\d*|\d*[+XVPI-]+)】\s*【", rev_name, re.IGNORECASE):
        return True
    # 匹配动漫绝对集号格式（如 Title - 02）
    if re.search(r"\s+-\s+[\dv]{1,4}\b", rev_name, re.IGNORECASE):
        return True
    # 排除电视剧集号格式
    if re.search(
        r"S\d{2}\s*-\s*S\d{2}|S\d{2}|\s+S\d{1,2}|EP?\d{2,4}\s*-\s*EP?\d{2,4}|\s+E\d{1,4}\b|\s+EP\d{1,4}\b",
        rev_name,
        re.IGNORECASE,
    ):
        return False
    # 匹配英文方括号标记：要求至少包含一个非数字字符，排除纯数字如 [12]
    return bool(re.search(r"\[(?:[+XVPI-]+\d*|\d*[+XVPI-]+)]\s*\[", rev_name, re.IGNORECASE))
