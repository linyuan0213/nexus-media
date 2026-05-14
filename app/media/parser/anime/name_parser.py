"""
动漫标题解析 — 名称解析
"""

import re

import zhconv

from app.media.parser.anime.constants import _ANIME_NO_WORDS, _NAME_NOSTRING_RE
from app.utils import StringUtils


def extract_name(info, anitopy_info, title):
    """从 anitopy 结果中提取名称"""
    name = anitopy_info.get("anime_title")
    if name and name.find("/") != -1:
        name = name.split("/")[-1].strip()
    if not name or name in _ANIME_NO_WORDS or (len(name) < 5 and not StringUtils.is_chinese(name)):
        import anitopy

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
        if word.endswith("]"):
            word = word[:-1]
        if word.isdigit():
            if lastword_type == "cn":
                info.cn_name = "%s %s" % (info.cn_name or "", word)
            elif lastword_type == "en":
                info.en_name = "%s %s" % (info.en_name or "", word)
        elif StringUtils.is_chinese(word):
            info.cn_name = "%s %s" % (info.cn_name or "", word)
            lastword_type = "cn"
        else:
            info.en_name = "%s %s" % (info.en_name or "", word)
            lastword_type = "en"


def clean_name(info):
    """清理并标准化名称"""
    if info.cn_name:
        _, info.cn_name, _, _, _, _ = StringUtils.get_keyword_from_string(info.cn_name)
        if info.cn_name:
            info.cn_name = re.sub(r"%s" % _NAME_NOSTRING_RE, "", info.cn_name, flags=re.IGNORECASE).strip()
            info.cn_name = zhconv.convert(info.cn_name, "zh-hans")
    if info.en_name:
        info.en_name = re.sub(r"%s" % _NAME_NOSTRING_RE, "", info.en_name, flags=re.IGNORECASE).strip().title()
        info._name = StringUtils.str_title(info.en_name)
