"""
站点搜索器 — 基于站点定义的统一搜索实现

替代各专用爬虫类（MteamSpider/RousiSpider/YemaPTSpider 等），
通过声明式 JSON 配置驱动搜索流程。
"""

import datetime
import os
import re
from collections.abc import Callable

import pytz

from app.utils.string_utils import StringUtils

_TRANSFORMS: dict[str, Callable] = {
    "mteam_labels": lambda val: _mteam_label(val),
    "yemapt_labels": lambda val: "|".join(
        [
            {"5": "国语", "6": "中字", "7": "粤语", "8": "英字"}.get(str(v), "")
            for v in (val if isinstance(val, list) else [])
        ]
    ),
    "utc_to_local": lambda val: _utc_to_local(val),
    "timestamp_to_date": lambda val: (
        datetime.datetime.fromtimestamp(val, pytz.timezone(os.environ.get("TZ", "Asia/Shanghai"))).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if val
        else ""
    ),
    "num_filesize_B": lambda val: StringUtils.num_filesize(f"{val}B") if val else "0",
}


def _utc_to_local(val):
    if not val:
        return ""
    try:
        dt_utc = datetime.datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        local_tz = pytz.timezone(os.environ.get("TZ", "Asia/Shanghai"))
        return dt_utc.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(val)


def _mteam_label(val):
    if not val:
        return ""
    label_map = {
        "1": "DIY",
        "2": "国配",
        "4": "中字",
        "3": "DIY|国配",
        "5": "DIY|中字",
        "6": "国配|中字",
        "7": "DIY|国配|中字",
    }
    if isinstance(val, list):
        return "|".join(label_map.get(str(v), "") for v in val)
    return label_map.get(str(val), "")


def _css_to_xpath(css: str) -> str:
    if not css or not css.strip():
        return "."
    css = css.strip()
    if css.startswith(("//", ".//")):
        return css

    def _convert_has(m):
        inner = m.group(1).strip()
        inner = inner.strip('"').strip("'")
        inner = _convert_has_inner(inner)
        return f"[.//{inner}]"

    def _convert_has_inner(s):
        s = re.sub(r"\.([\w-]+)", r'[contains(@class,"\1")]', s)
        s = re.sub(r"#([\w-]+)", r'[@id="\1"]', s)
        s = re.sub(r'\[(\w+)\*=["\']?(.+?)["\']?\]', r'[contains(@\1,"\2")]', s)
        if not re.match(r"[a-zA-Z\*]", s):
            s = "*" + s
        return s

    sel = css
    sel = re.sub(r":has\(([^()]*(?:\([^()]*\))*[^()]*)\)", _convert_has, sel)
    sel = re.sub(r'\[(\w+)\*=["\']?(.+?)["\']?\]', r'[contains(@\1,"\2")]', sel)
    sel = re.sub(r":nth-child\((\d+)\)", r"[\1]", sel)

    parts = [p.strip() for p in sel.split(">")]
    full = []
    for pi, part in enumerate(parts):
        if not part:
            continue
        subparts = part.split()
        for i, sp in enumerate(subparts):
            if not sp:
                continue
            converted = sp
            converted = re.sub(r"\.([\w-]+)", r'[contains(@class,"\1")]', converted)
            converted = re.sub(r"#([\w-]+)", r'[@id="\1"]', converted)
            converted = re.sub(r"\[([a-zA-Z\-_]+)\]", r"[@\1]", converted)
            converted = re.sub(r'\[([a-zA-Z\-_]+)="([^"]*)"\]', r'[@\1="\2"]', converted)
            if pi == 0 and i == 0:
                tag = ".//"
            elif i == 0:
                tag = "/"
            else:
                tag = "//"
            if not re.match(r"[a-zA-Z\*]", converted):
                converted = "*" + converted
            full.append(tag + converted)
    return "".join(full)


def _resolve_jinja(text: str, fields: dict) -> str:
    if not text or "{%" not in text:
        text = re.sub(r"\{\{\s*fields\[[\"'](\w+)[\"']\]\s*\}\}", lambda m: str(fields.get(m.group(1), "")), text)
        return text
    cond_match = re.search(
        r"\{%\s*if\s+fields\[[\"'](\w+)[\"']\]\s*%\}(.+?)\{%\s*else\s*%\}(.+?)\{%\s*endif\s*%\}",
        text,
        re.DOTALL,
    )
    if cond_match:
        cond_field = cond_match.group(1)
        true_text = cond_match.group(2).strip()
        false_text = cond_match.group(3).strip()
        replacement = true_text if fields.get(cond_field) else false_text
        replacement = re.sub(
            r"\{\{\s*fields\[[\"'](\w+)[\"']\]\s*\}\}", lambda m: str(fields.get(m.group(1), "")), replacement
        )
        text = text[: cond_match.start()] + replacement + text[cond_match.end() :]
        return _resolve_jinja(text, fields)
    return re.sub(r"\{\{\s*fields\[[\"'](\w+)[\"']\]\s*\}\}", lambda m: str(fields.get(m.group(1), "")), text)
