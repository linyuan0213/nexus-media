"""
影视标题解析 — 分辨率、资源类型、Part解析
"""

import re

from app.media.parser.video.constants import (
    _effect_re,
    _part_re,
    _resources_pix_re,
    _resources_pix_re2,
    _source_re,
)


def init_part(info, token, tokens):
    """解析 PART/CD/DVD/DISK/DISC"""
    if not info.get_name():
        return
    if (
        not info.year
        and not info.begin_season
        and not info.begin_episode
        and not info.resource_pix
        and not info.resource_type
    ):
        return
    re_res = re.search(rf"{_part_re}", token, re.IGNORECASE)
    if re_res:
        if not info.part:
            info.part = re_res.group(1)
        nextv = tokens.cur()
        if nextv and (
            (nextv.isdigit() and (len(nextv) == 1 or len(nextv) == 2 and nextv.startswith("0")))
            or nextv.upper() in ["A", "B", "C", "I", "II", "III"]
        ):
            info.part = f"{info.part}{nextv}"
            tokens.get_next()
        info._last_token_type = "part"
        info._continue_flag = False
        info._stop_name_flag = False


def init_resource_pix(info, token):
    """解析分辨率"""
    if not info.get_name():
        return
    re_res = re.findall(rf"{_resources_pix_re}", token, re.IGNORECASE)
    if re_res:
        info._last_token_type = "pix"
        info._continue_flag = False
        info._stop_name_flag = True
        resource_pix = None
        for pixs in re_res:
            if isinstance(pixs, tuple):
                pix_t = None
                for pix_i in pixs:
                    if pix_i:
                        pix_t = pix_i
                        break
                if pix_t:
                    resource_pix = pix_t
            else:
                resource_pix = pixs
            if resource_pix and not info.resource_pix:
                info.resource_pix = resource_pix.lower()
                break
        if info.resource_pix and info.resource_pix.isdigit() and info.resource_pix[-1] not in "kpi":
            info.resource_pix = f"{info.resource_pix}p"
    else:
        re_res = re.search(rf"{_resources_pix_re2}", token, re.IGNORECASE)
        if re_res:
            info._last_token_type = "pix"
            info._continue_flag = False
            info._stop_name_flag = True
            if not info.resource_pix:
                info.resource_pix = re_res.group(1).lower()


def init_resource_type(info, token):
    """解析来源和效果"""
    if not info.get_name():
        return
    source_res = re.search(rf"({_source_re})", token, re.IGNORECASE)
    if source_res:
        info._last_token_type = "source"
        info._continue_flag = False
        info._stop_name_flag = True
        if not info._source:
            info._source = source_res.group(1)
            info._last_token = info._source.upper()
        return
    elif token.upper() == "DL" and info._last_token_type == "source" and info._last_token == "WEB":
        info._source = "WEB-DL"
        info._continue_flag = False
        return
    elif token.upper() == "RAY" and info._last_token_type == "source" and info._last_token == "BLU":
        info._source = "BluRay"
        info._continue_flag = False
        return
    elif token.upper() == "WEBDL":
        info._source = "WEB-DL"
        info._continue_flag = False
        return
    effect_res = re.search(rf"({_effect_re})", token, re.IGNORECASE)
    if effect_res:
        info._last_token_type = "effect"
        info._continue_flag = False
        info._stop_name_flag = True
        effect = effect_res.group(1)
        if effect not in info._effect:
            info._effect.append(effect)
        info._last_token = effect.upper()
