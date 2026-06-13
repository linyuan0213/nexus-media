"""中文处理工具函数."""

import opencc


_to_simplified = opencc.OpenCC("tw2sp")


def to_simplified(text: str | None) -> str:
    """将繁体中文转换为简体中文（含台湾常用词汇转换）.

    :param text: 输入文本
    :return: 简体中文文本；输入为空时返回空字符串
    """
    if not text:
        return ""
    return _to_simplified.convert(text)
