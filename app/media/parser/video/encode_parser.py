"""
影视标题解析 — 视频/音频编码解析
"""

import re

from app.media.parser.video.constants import _audio_encode_re, _video_encode_re


def init_video_encode(info, token):
    """解析视频编码"""
    if not info.get_name():
        return
    if (
        not info.year
        and not info.resource_pix
        and not info.resource_type
        and not info.begin_season
        and not info.begin_episode
    ):
        return
    re_res = re.search(r"(%s)" % _video_encode_re, token, re.IGNORECASE)
    if re_res:
        info._continue_flag = False
        info._stop_name_flag = True
        info._last_token_type = "videoencode"
        if not info.video_encode:
            info.video_encode = re_res.group(1).upper()
            info._last_token = info.video_encode
        elif info.video_encode == "10bit":
            info.video_encode = f"{re_res.group(1).upper()} 10bit"
            info._last_token = re_res.group(1).upper()
    elif token.upper() in ["H", "X"]:
        info._continue_flag = False
        info._stop_name_flag = True
        info._last_token_type = "videoencode"
        info._last_token = token.upper() if token.upper() == "H" else token.lower()
    elif (
        token in ["264", "265"]
        and info._last_token_type == "videoencode"
        and info._last_token in ["H", "X"]
        or token.isdigit()
        and info._last_token_type == "videoencode"
        and info._last_token in ["VC", "MPEG"]
    ):
        info.video_encode = "%s%s" % (info._last_token, token)
    elif token.upper() == "10BIT":
        info._last_token_type = "videoencode"
        if not info.video_encode:
            info.video_encode = "10bit"
        else:
            info.video_encode = f"{info.video_encode} 10bit"


def init_audio_encode(info, token):
    """解析音频编码"""
    if not info.get_name():
        return
    if (
        not info.year
        and not info.resource_pix
        and not info.resource_type
        and not info.begin_season
        and not info.begin_episode
    ):
        return
    re_res = re.search(r"(%s)" % _audio_encode_re, token, re.IGNORECASE)
    if re_res:
        info._continue_flag = False
        info._stop_name_flag = True
        info._last_token_type = "audioencode"
        info._last_token = re_res.group(1).upper()
        if not info.audio_encode:
            info.audio_encode = re_res.group(1)
        else:
            if info.audio_encode.upper() == "DTS":
                info.audio_encode = "%s-%s" % (info.audio_encode, re_res.group(1))
            else:
                info.audio_encode = "%s %s" % (info.audio_encode, re_res.group(1))
    elif token.isdigit() and info._last_token_type == "audioencode":
        if info.audio_encode:
            if info._last_token.isdigit():
                info.audio_encode = "%s.%s" % (info.audio_encode, token)
            elif info.audio_encode[-1].isdigit():
                info.audio_encode = "%s %s.%s" % (info.audio_encode[:-1], info.audio_encode[-1], token)
            else:
                info.audio_encode = "%s %s" % (info.audio_encode, token)
        info._last_token = token
