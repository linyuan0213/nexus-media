import os.path
from typing import Any

import regex as re

import log
from app.core.constants import RMT_MEDIAEXT
from app.domain.mediatypes import MediaType
from app.domain.word_processor import get_words_info, process_title
from app.media.parser._anime import parse_anime_title
from app.media.parser._video import parse_video_title


def meta_info(title: str, subtitle: str | None = None, mtype: MediaType | None = None) -> Any:
    org_title = title
    if title:
        cleaned = re.sub(
            r"(?i)\b(?:www\s+\w+|\w+\.(?:com|net|org|tv|cc|me|io)\b|pthdtv|qqhdtv|剧集网发布)\b",
            "",
            title,
        )
        cleaned = re.sub(r"\[\s*[^\]]*(?:发布|字幕组|翻译组)[^\]]*\]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned != title:
            title = cleaned

    words = get_words_info()
    rev_title, msg, used_info = process_title(words, title)
    if subtitle:
        subtitle, _, _ = process_title(words, subtitle)

    if msg:
        for msg_item in msg:
            log.warn(f"[Meta]{msg_item}")

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

    if media_info.begin_episode and org_title:
        if re.search(rf"{media_info.begin_episode}\s*(FPS|HZ)", org_title, re.IGNORECASE):
            media_info.begin_episode = None
            media_info.end_episode = None
            media_info.total_episodes = 0

    return media_info


def _is_anime(rev_name: str, org_name: str) -> bool:
    rev_name = re.sub(r"\[[0-9A-F]{8}]", "", rev_name, flags=re.IGNORECASE)
    org_name = re.sub(r"\[[0-9A-F]{8}]", "", org_name, flags=re.IGNORECASE)
    for name in (rev_name, org_name):
        if name and re.search(r"(?:SEX|HENTAI|AV\b|無码|R18|成人)", name, re.IGNORECASE):
            return False
    if not rev_name:
        return False
    if re.search(r"\[(?:[+XVPI-]+\d*|\d*[+XVPI-]+)]\s*\[", rev_name, re.IGNORECASE):
        return True
    if re.search(r"\s+-\s+[\dv]{1,4}\b", rev_name, re.IGNORECASE):
        return True
    if re.search(
        r"S\d{2}\s*-\s*S\d{2}|S\d{2}|\s+S\d{1,2}|EP?\d{2,4}\s*-\s*EP?\d{2,4}|\s+E\d{1,4}\b|\s+EP\d{1,4}\b",
        rev_name,
        re.IGNORECASE,
    ):
        return False
    if re.search(r"\[(?:[+XVPI-]+\d*|\d*[+XVPI-]+)]\s*\[", rev_name, re.IGNORECASE):
        return True
    return False
