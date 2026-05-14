"""Discuz 架构用户信息解析"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lxml import etree

from app.utils import StringUtils

if TYPE_CHECKING:
    from app.sites.siteuserinfo.config_html import ConfigHtmlUserInfo


def is_discuz(ins: ConfigHtmlUserInfo) -> bool:
    return "Powered by Discuz!" in ins._index_html


def parse(ins: ConfigHtmlUserInfo) -> None:
    html_text = re.sub(r"#\d+", "", re.sub(r"\d+px", "", ins._index_html))
    html = etree.HTML(html_text)
    if html is None:
        return

    user_info = html.xpath('//a[contains(@href, "&uid=")]')
    if user_info:
        m = re.search(r"&uid=(\d+)", user_info[0].attrib["href"])
        if m:
            uid = m.group(1)
            if uid and uid.strip():
                ins.userid = uid
                ins.username = (user_info[0].text or "").strip()

    level = html.xpath('//a[contains(@href, "usergroup")]/text()')
    if level:
        ins.user_level = level[-1].strip()

    join = html.xpath('//li[em[text()="注册时间"]]/text()')
    if join:
        ins.join_at = StringUtils.unify_datetime_str(join[0].strip())

    bonus = html.xpath('//li[em[text()="积分"]]/text()')
    if bonus:
        ins.bonus = StringUtils.str_float(bonus[0].strip())

    upload = html.xpath('//li[em[contains(text(),"上传量")]]/text()')
    if upload:
        ins.upload = StringUtils.num_filesize(upload[0].strip().split("/")[-1])

    download = html.xpath('//li[em[contains(text(),"下载量")]]/text()')
    if download:
        ins.download = StringUtils.num_filesize(download[0].strip().split("/")[-1])

    ins.ratio = 0.0 if ins.download <= 0.0 else round(ins.upload / ins.download, 3)
