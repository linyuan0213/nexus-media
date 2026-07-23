"""
动漫标题解析 — 名称解析
"""

import re

import anitopy  # type: ignore

from app.media.parser.anime.constants import _ANIME_NO_WORDS, _NAME_CLEANUP_RE, _NAME_NOSTRING_RE
from app.utils import StringUtils
from app.utils.chinese_utils import to_simplified


def extract_name(info, anitopy_info, title):
    """从 anitopy 结果中提取名称"""
    name = anitopy_info.get("anime_title")
    if name and name.find("/") != -1:
        parts = [p.strip() for p in name.split("/")]
        left = parts[0]
        right = parts[-1]
        if StringUtils.is_chinese(left) and not StringUtils.is_all_chinese(right):
            info.cn_name = left
            name = right
        elif not StringUtils.is_chinese(right) or len(parts) > 1:
            name = right if not StringUtils.is_all_chinese(right) else left
    if not name or name in _ANIME_NO_WORDS or (len(name) < 5 and not StringUtils.is_chinese(name)):
        anitopy_info = anitopy.parse("[ANIME]" + title)
        if anitopy_info:
            name = anitopy_info.get("anime_title")
    if not name or name in _ANIME_NO_WORDS or (len(name) < 5 and not StringUtils.is_chinese(name)):
        name_match = re.search(r"\[(.+?)]", title)
        if name_match and name_match.group(1):
            name = name_match.group(1).strip()
    return name


def parse_name(info, name):
    """拆份中英文名称"""
    if not name:
        return
    lastword_type = ""
    for word in name.split():
        if not word:
            continue
        word = word.removesuffix("]")
        if word.isdigit():
            if lastword_type == "cn":
                info.cn_name = "{} {}".format(info.cn_name or "", word)
            elif lastword_type == "en":
                info.en_name = "{} {}".format(info.en_name or "", word)
        elif StringUtils.is_chinese(word):
            info.cn_name = "{} {}".format(info.cn_name or "", word)
            lastword_type = "cn"
        else:
            info.en_name = "{} {}".format(info.en_name or "", word)
            lastword_type = "en"


def clean_name(info):
    """清理并标准化名称"""
    if info.cn_name:
        _, info.cn_name, _, _, _, _ = StringUtils.get_keyword_from_string(info.cn_name)
        if info.cn_name:
            info.cn_name = re.sub(rf"{_NAME_NOSTRING_RE}", "", info.cn_name, flags=re.IGNORECASE).strip()
            info.cn_name = re.sub(_NAME_CLEANUP_RE, "", info.cn_name, flags=re.IGNORECASE).strip()
            info.cn_name = to_simplified(info.cn_name)
    if info.en_name:
        info.en_name = re.sub(rf"{_NAME_NOSTRING_RE}", "", info.en_name, flags=re.IGNORECASE).strip()
        info.en_name = re.sub(_NAME_CLEANUP_RE, "", info.en_name, flags=re.IGNORECASE).strip()
        info.en_name = info.en_name.title()
        info._name = StringUtils.str_title(info.en_name)
