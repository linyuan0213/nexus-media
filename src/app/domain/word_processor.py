"""识别词处理器 — 纯领域逻辑，无外部服务依赖."""

import ast
import re

import cn2an
import regex as regex_mod

from app.utils.exception_utils import ExceptionUtils

# 模块级缓存，由 services/words_service 在初始化时注入
_words_info: list = []


def set_words_info(words: list) -> None:
    """由上层模块注入识别词数据."""
    global _words_info
    _words_info = words


def get_words_info() -> list:
    return _words_info


def process_title(words_info: list, title: str) -> tuple[str, list[str], dict]:
    """
    对标题应用识别词规则（屏蔽、替换、集偏移）。

    :param words_info: 已加载的识别词列表
    :param title: 待处理标题
    :return: (处理后的标题, 消息列表, 使用情况字典)
    """
    msg: list[str] = []
    used_ignored: list[str] = []
    used_replaced: list[str] = []
    used_offset: list[str] = []

    for word_info in words_info:
        match word_info.TYPE:
            case 1:
                ignored = word_info.REPLACED
                title, ignore_msg, ignore_flag = (
                    _replace_regex(title, ignored, "") if word_info.REGEX else _replace_noregex(title, ignored, "")
                )
                if ignore_flag:
                    used_ignored.append(ignored)
                elif ignore_msg:
                    msg.append(f"自定义屏蔽词 {ignored} 设置有误：{ignore_msg}")
            case 2:
                replaced, replace = word_info.REPLACED, word_info.REPLACE
                replaced_word = f"{replaced} ⇒ {replace}"
                title, replace_msg, replace_flag = (
                    _replace_regex(title, replaced, replace)
                    if word_info.REGEX
                    else _replace_noregex(title, replaced, replace)
                )
                if replace_flag:
                    used_replaced.append(replaced_word)
                elif replace_msg:
                    msg.append(f"自定义替换词 {replaced_word} 格式有误：{replace_msg}")
            case 3:
                replaced, replace, front, back, offset = (
                    word_info.REPLACED,
                    word_info.REPLACE,
                    word_info.FRONT,
                    word_info.BACK,
                    word_info.OFFSET,
                )
                replaced_word = f"{replaced} ⇒ {replace}"
                offset_word = f"{front} + {back} >> {offset}"
                title_cache = title
                title, replace_msg, replace_flag = _replace_regex(title, replaced, replace)
                if replace_flag:
                    title, offset_msg, offset_flag = _episode_offset(title, front, back, offset)
                    if offset_flag:
                        used_replaced.append(replaced_word)
                        used_offset.append(offset_word)
                    elif offset_msg:
                        title = title_cache
                        msg.append(
                            f"自定义替换+集偏移词 {replaced_word} @@@ {offset_word} 集偏移部分格式有误：{offset_msg}"
                        )
                elif replace_msg:
                    msg.append(f"自定义替换+集偏移词 {replaced_word} @@@ {offset_word} 替换部分格式有误：{replace_msg}")
            case 4:
                front, back, offset = word_info.FRONT, word_info.BACK, word_info.OFFSET
                offset_word = f"{front} + {back} >> {offset}"
                title, offset_msg, offset_flag = _episode_offset(title, front, back, offset)
                if offset_flag:
                    used_offset.append(offset_word)
                elif offset_msg:
                    msg.append(f"自定义集偏移词 {offset_word} 格式有误：{offset_msg}")
            case _:
                pass

    return title, msg, {"ignored": used_ignored, "replaced": used_replaced, "offset": used_offset}


def _replace_regex(title: str, replaced: str, replace: str) -> tuple[str, str, bool]:
    try:
        if not regex_mod.findall(rf"{replaced}", title):
            return title, "", False
        return regex_mod.sub(rf"{replaced}", rf"{replace}", title), "", True
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        return title, str(err), False


def _replace_noregex(title: str, replaced: str, replace: str) -> tuple[str, str, bool]:
    try:
        if title.find(replaced) == -1:
            return title, "", False
        return title.replace(replaced, replace), "", True
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        return title, str(err), False


def _episode_offset(title: str, front: str, back: str, offset: str) -> tuple[str, str, bool]:
    try:
        if back and not regex_mod.findall(rf"{back}", title):
            return title, "", False
        if front and not regex_mod.findall(rf"{front}", title):
            return title, "", False
        offset_word_info_re = regex_mod.compile(rf"(?<={front}.*?)[0-9一二三四五六七八九十]+(?=.*?{back})")
        episode_nums_str = regex_mod.findall(offset_word_info_re, title)
        if not episode_nums_str:
            return title, "", False
        episode_nums_offset_str = []
        offset_order_flag = False
        for episode_num_str in episode_nums_str:
            episode_num_int = int(cn2an.cn2an(episode_num_str, "smart"))
            offset_caculate = offset.replace("EP", str(episode_num_int))
            episode_num_offset_int = int(ast.literal_eval(offset_caculate))
            if episode_num_int > episode_num_offset_int:
                offset_order_flag = True
            elif episode_num_int < episode_num_offset_int:
                offset_order_flag = False
            if not episode_num_str.isdigit():
                episode_num_offset_str = cn2an.an2cn(episode_num_offset_int, "low")
            else:
                count_0 = re.findall(r"^0+", episode_num_str)
                if count_0:
                    episode_num_offset_str = f"{count_0[0]}{episode_num_offset_int}"
                else:
                    episode_num_offset_str = str(episode_num_offset_int)
            episode_nums_offset_str.append(episode_num_offset_str)
        episode_nums_dict = dict(zip(episode_nums_str, episode_nums_offset_str, strict=False))
        if offset_order_flag:
            episode_nums_list = sorted(episode_nums_dict.items(), key=lambda x: x[1])
        else:
            episode_nums_list = sorted(episode_nums_dict.items(), key=lambda x: x[1], reverse=True)
        for episode_num in episode_nums_list:
            episode_offset_re = regex_mod.compile(rf"(?<={front}.*?){episode_num[0]}(?=.*?{back})")
            title = regex_mod.sub(episode_offset_re, rf"{episode_num[1]}", title)
        return title, "", True
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        return title, str(err), False
