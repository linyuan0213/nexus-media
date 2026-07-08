"""
影视标题解析 — 主入口
将 MetaVideo 类拆分为纯函数模块
"""

import os
import re

from app.core.constants import RMT_MEDIAEXT
from app.domain.mediatypes import MediaType
from app.media.models import MediaInfo
from app.media.parser._customization import CustomizationMatcher
from app.media.parser._release_groups import ReleaseGroupsMatcher
from app.media.parser.video.encode_parser import init_audio_encode, init_video_encode
from app.media.parser.video.name_parser import fix_name, init_name
from app.media.parser.video.resource_parser import init_part, init_resource_pix, init_resource_type
from app.media.parser.video.season_episode_parser import init_episode, init_season, init_year
from app.utils import StringUtils
from app.utils.tokens import Tokens


def parse_video_title(
    title, subtitle=None, fileflag=False, customization_matcher: CustomizationMatcher | None = None
) -> MediaInfo:
    """解析影视文件名，返回 MediaInfo"""
    info = MediaInfo()
    if not title:
        return info
    info.org_string = title
    info.subtitle = subtitle
    info.fileflag = fileflag
    original_title = title
    info._source = ""
    info._effect = []
    info._stop_name_flag = False
    info._stop_cnname_flag = False
    info._last_token = ""
    info._last_token_type = ""
    info._continue_flag = True
    info._unknown_name_str = ""

    # 预处理：移除 FPS/Hz 参数，避免被误判为集数（如 120FPS → E120）
    title = re.sub(r"\d+\s*(FPS|HZ)\b", "", title, flags=re.IGNORECASE)

    # 判断是否纯数字命名
    if (
        os.path.splitext(title)[-1] in RMT_MEDIAEXT
        and os.path.splitext(title)[0].isdigit()
        and len(os.path.splitext(title)[0]) < 5
    ):
        info.begin_episode = int(os.path.splitext(title)[0])
        info.type = MediaType.TV
        return info

    # 预处理字幕组 episode 标注格式: [XX - 总第YY] → 提取 XX 作为 episode
    re_res = re.search(r"\[(\d{1,3})\s*-\s*总第\d{1,3}\]", title)
    if re_res:
        info.begin_episode = int(re_res.group(1))
        info.type = MediaType.TV

    # 预处理中文方括号集号: [XX] → 提取 XX 作为 episode
    if not info.begin_episode:
        re_res = re.search(r"\[(\d{1,3})\]", title)
        if re_res:
            info.begin_episode = int(re_res.group(1))
            info.type = MediaType.TV

    # 预处理绝对集号格式: "Title - XX [tags]" / "Title - XX 1080p" / "Title - XX.mkv" → 提取 XX 作为 episode
    if not info.begin_episode:
        re_res = re.search(r"\s-\s(\d{1,3})\b", title)
        if re_res:
            info.begin_episode = int(re_res.group(1))
            info.type = MediaType.TV

    # 预处理
    # 移除开头的方括号标签：
    #   - 纯非中日韩内容（如 [HDArea]、[FRDS]）视为发布组 → 移除
    #   - 含「字幕/压制/制作组/发布组/站点域名」等特征的中文标签（如 [XX字幕组]、[电影天堂www.dy.com]）→ 移除
    #   - 其余含中日韩文的方括号（如 [虚颜]、[庆余年]）视为剧名 → 保留，避免只剩英文名而误配
    _begin_bracket = re.match(r"^\[(.+?)]", title)
    if _begin_bracket:
        _inner = _begin_bracket.group(1)
        _has_cjk = bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]", _inner))
        _looks_like_group = bool(
            re.search(
                r"字幕|压制|制作组|发布组|字幕社|工作室|论坛|www\.|\.(?:com|net|cc|org|tv)", _inner, re.IGNORECASE
            )
        )
        if not _has_cjk or _looks_like_group:
            title = title[_begin_bracket.end() :]
    title = re.sub(r"([\s.]+)(\d{4})-(\d{4})", r"\1\2", title)
    title = re.sub(r"[0-9.]+\s*[MGT]i?B(?![A-Z]+)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\d{4}[\s._-]\d{1,2}[\s._-]\d{1,2}", "", title)

    # 拆分 tokens
    tokens = Tokens(title)
    token = tokens.get_next()
    while token:
        init_part(info, token, tokens)
        if info._continue_flag:
            init_name(info, token)
        if info._continue_flag:
            init_year(info, token)
        if info._continue_flag:
            init_resource_pix(info, token)
        if info._continue_flag:
            init_season(info, token)
        if info._continue_flag:
            init_episode(info, token)
        if info._continue_flag:
            init_resource_type(info, token)
        if info._continue_flag:
            init_video_encode(info, token)
        if info._continue_flag:
            init_audio_encode(info, token)
        token = tokens.get_next()
        info._continue_flag = True

    # 合成质量
    if info._effect:
        info._effect.reverse()
        info.resource_effect = " ".join(info._effect)
    if info._source:
        info.resource_type = info._source.strip()

    # 提取原盘DIY
    if info.resource_type and "BluRay" in info.resource_type:
        if (info.subtitle and re.findall(r"D[Ii]Y", info.subtitle)) or re.findall(r"-D[Ii]Y@", original_title):
            info.resource_type = f"{info.resource_type} DIY"

    # 解析副标题
    if not _subtitle_changed(info, info.org_string) and info.subtitle:
        info.init_subtitle(info.subtitle)

    # 默认类型
    if not info.type:
        info.type = MediaType.MOVIE

    # 清理名称
    info.cn_name = fix_name(info, info.cn_name)
    info.en_name = StringUtils.str_title(fix_name(info, info.en_name))

    # 处理 part
    if info.part and info.part.upper() == "PART":
        info.part = None

    # 制作组/字幕组
    info.resource_team = ReleaseGroupsMatcher().match(title=original_title) or None
    matcher = customization_matcher or CustomizationMatcher()
    info.customization = matcher.match(title=original_title) or None
    return info


def _subtitle_changed(info, title_text):
    """检测副标题解析是否修改了信息"""
    before = (
        info.begin_season,
        info.end_season,
        info.total_seasons,
        info.begin_episode,
        info.end_episode,
        info.total_episodes,
        info.type,
    )
    info.init_subtitle(title_text)
    after = (
        info.begin_season,
        info.end_season,
        info.total_seasons,
        info.begin_episode,
        info.end_episode,
        info.total_episodes,
        info.type,
    )
    return before != after
