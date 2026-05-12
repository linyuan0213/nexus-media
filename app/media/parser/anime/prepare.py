# -*- coding: utf-8 -*-
"""
动漫标题解析 — 预处理函数
"""
import re

import zhconv

from app.utils import StringUtils


def prepare_title(title):
    """对命名进行预处理"""
    if not title:
        return title
    title = title.replace("【", "[").replace("】", "]").strip()
    match = re.search(r"新番|月?番|[日美国][漫剧]", title)
    if match and match.span()[1] < len(title) - 1:
        title = re.sub(".*番.|.*[日美国][漫剧].", "", title)
    elif match:
        title = title[:title.rfind('[')]
    first_item = title.split(']')[0]
    if first_item and re.search(r"[动漫画纪录片电影视连续剧集日美韩中港台海外亚洲华语大陆综艺原盘高清]{2,}|TV|Animation|Movie|Documentar|Anime",
                                zhconv.convert(first_item, "zh-hans"),
                                re.IGNORECASE):
        title = re.sub(r"^[^]]*]", "", title).strip()
    title = re.sub(r'[0-9.]+\s*[MGT]i?B(?![A-Z]+)', "", title, flags=re.IGNORECASE)
    title = re.sub(r"\[TV\s+(\d{1,4})", r"[\1", title, flags=re.IGNORECASE)
    title = re.sub(r'\[4k]', '2160p', title, flags=re.IGNORECASE)
    names = title.split("]")
    if len(names) > 1 and title.find("- ") == -1:
        titles = []
        for name in names:
            if not name:
                continue
            left_char = ''
            if name.startswith('['):
                left_char = '['
                name = name[1:]
            if name and name.find("/") != -1:
                if name.split("/")[-1].strip():
                    titles.append("%s%s" % (left_char, name.split("/")[-1].strip()))
                else:
                    titles.append("%s%s" % (left_char, name.split("/")[0].strip()))
            elif name:
                if StringUtils.is_chinese(name) and not StringUtils.is_all_chinese(name):
                    if not re.search(r"\[\d+", name, re.IGNORECASE):
                        name = re.sub(r'[\d|#:：\-()（）\u4e00-\u9fff]', '', name).strip()
                    if not name or name.strip().isdigit():
                        continue
                if name == '[':
                    titles.append("")
                else:
                    titles.append("%s%s" % (left_char, name.strip()))
        return "]".join(titles)
    return title
