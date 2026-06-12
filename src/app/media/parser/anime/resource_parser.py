"""
动漫标题解析 — 分辨率、编码、制作组解析
"""

import re

from app.media.parser._customization import CustomizationMatcher
from app.media.parser._release_groups import ReleaseGroupsMatcher


def parse_resource_pix(info, anitopy_info):
    """解析分辨率"""
    info.resource_pix = anitopy_info.get("video_resolution")
    if isinstance(info.resource_pix, list):
        info.resource_pix = info.resource_pix[0]
    if info.resource_pix:
        if re.search(r"x", info.resource_pix, re.IGNORECASE):
            info.resource_pix = re.split(r"[Xx]", info.resource_pix)[-1] + "p"
        else:
            info.resource_pix = info.resource_pix.lower()
        if str(info.resource_pix).isdigit():
            info.resource_pix = str(info.resource_pix) + "p"


def parse_team(info, original_title, anitopy_info_origin):
    """解析制作组/字幕组"""
    info.resource_team = (
        ReleaseGroupsMatcher().match(title=original_title) or anitopy_info_origin.get("release_group") or None
    )


def parse_customization(info, original_title, customization_matcher: CustomizationMatcher | None = None):
    """解析自定义占位符"""
    matcher = customization_matcher or CustomizationMatcher()
    info.customization = matcher.match(title=original_title) or None


def parse_encode(info, anitopy_info):
    """解析视频/音频编码"""
    info.video_encode = anitopy_info.get("video_term")
    if isinstance(info.video_encode, list):
        info.video_encode = info.video_encode[0]
    info.audio_encode = anitopy_info.get("audio_term")
    if isinstance(info.audio_encode, list):
        info.audio_encode = info.audio_encode[0]
