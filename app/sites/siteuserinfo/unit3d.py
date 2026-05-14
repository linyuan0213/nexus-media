"""Unit3d 架构用户信息解析"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from lxml import etree

from app.utils import StringUtils

if TYPE_CHECKING:
    from app.sites.siteuserinfo.config_html import ConfigHtmlUserInfo


def is_unit3d(ins: ConfigHtmlUserInfo) -> bool:
    return "unit3d.js" in ins._index_html


def parse(ins: ConfigHtmlUserInfo) -> None:
    html_text = re.sub(r"#\d+", "", re.sub(r"\d+px", "", ins._index_html))
    html = etree.HTML(html_text)
    if html is None:
        return

    tmps = html.xpath('//a[contains(@href,"/users/") and contains(@href,"settings")]/@href')
    if tmps:
        m = re.search(r"/users/(.+)/settings", str(tmps[0]))
        if m and m.group(1).strip():
            ins.username = m.group(1)

    level = html.xpath('//div[contains(@class,"content")]//span[contains(@class,"badge-user")]/text()')
    if level:
        ins.user_level = level[0].strip()

    bonus_el = html.xpath('//a[contains(@href,"bonus/earnings")]')
    if bonus_el:
        bt = bonus_el[0].xpath("string(.)")
        bm = re.search(r"([\d,.]+)", str(bt))
        if bm and bm.group(1).strip():
            ins.bonus = StringUtils.str_float(bm.group(1))

    join = html.xpath(
        '//div[contains(@class,"content")]//h4[contains(text(),"注册日期") '
        'or contains(text(),"Registration date")]/text()'
    )
    if join:
        join_text = str(join[0] or "")
        ins.join_at = StringUtils.unify_datetime_str(join_text.replace("注册日期", "").replace("Registration date", ""))

    username = getattr(ins, "username", None) or ""
    if not username:
        return
    profile_url = urljoin(ins._base_url_str + "/", f"users/{username}")
    profile_text = ins._fetch_html(profile_url)
    if not profile_text:
        return
    profile_doc = etree.HTML(profile_text)
    if profile_doc is None:
        return

    _extract_traffic(ins, profile_doc)
    _extract_seeding(ins, profile_doc)


def _extract_traffic(ins: ConfigHtmlUserInfo, doc: etree._Element) -> None:
    for label, attr, is_size in [("Upload", "upload", True), ("Download", "download", True)]:
        vals = doc.xpath(
            f'//h4[contains(text(),"{label}")]/following-sibling::span[1]/text()'
            f'|//h4[contains(text(),"{label}")]/..//span//text()'
        )
        if vals:
            val = "".join(str(v) for v in vals).strip()
            setattr(ins, attr, StringUtils.num_filesize(val) if is_size else StringUtils.str_float(val))

    if not ins.upload:
        for pat in [
            '//span[contains(@class,"text-green") or contains(@class,"text-success")]//text()',
            '//td[contains(text(),"Upload") or contains(text(),"上传")]/following-sibling::td[1]//text()',
        ]:
            vals = doc.xpath(pat)
            for v in vals:
                val = "".join(v).strip() if isinstance(v, list) else str(v).strip()
                if re.search(r"[\d,.]+ *[KMGTP]i?B", val, re.I):
                    ins.upload = StringUtils.num_filesize(val)
                    break
            if ins.upload:
                break

    if not ins.download:
        for pat in [
            '//span[contains(@class,"text-red") or contains(@class,"text-danger")]//text()',
            '//td[contains(text(),"Download") or contains(text(),"下载")]/following-sibling::td[1]//text()',
        ]:
            vals = doc.xpath(pat)
            for v in vals:
                val = "".join(v).strip() if isinstance(v, list) else str(v).strip()
                if re.search(r"[\d,.]+ *[KMGTP]i?B", val, re.I):
                    ins.download = StringUtils.num_filesize(val)
                    break
            if ins.download:
                break

    ins.ratio = 0.0 if ins.download <= 0.0 else round(ins.upload / ins.download, 3)

    if not ins.join_at:
        join = doc.xpath(
            '//h4[contains(text(),"注册日期") or contains(text(),"Registration date")]'
            "/following-sibling::span[1]/text()"
            '|//h4[contains(text(),"注册日期") or contains(text(),"Registration date")]/text()'
        )
        if join:
            join_text = str(join[0] or "")
            ins.join_at = StringUtils.unify_datetime_str(
                join_text.replace("注册日期", "").replace("Registration date", "").strip()
            )

    if not ins.bonus:
        for pat in [
            '//a[contains(@href,"bonus")]/text()',
            '//a[contains(@href,"bonus")]/@data-tooltip',
            '//span[contains(text(),"BON") or contains(text(),"Bonus")]//text()',
        ]:
            for val in doc.xpath(pat):
                bm = re.search(r"([\d,.]+)", str(val))
                if bm and bm.group(1).strip():
                    v = StringUtils.str_float(bm.group(1))
                    if v > 0:
                        ins.bonus = v
                        break
            if ins.bonus:
                break


def _extract_seeding(ins: ConfigHtmlUserInfo, doc: etree._Element) -> None:
    for label, attr in [("Seeding", "seeding"), ("Leeching", "leeching")]:
        vals = doc.xpath(
            f'//h4[contains(text(),"{label}")]/following-sibling::span[1]/text()'
            f'|//h4[contains(text(),"{label}")]/..//span//text()'
        )
        if vals:
            val = "".join(str(v) for v in vals).strip()
            m = re.search(r"(\d+)", val)
            if m:
                setattr(ins, attr, StringUtils.str_int(m.group(1)))

    if not ins.seeding:
        vals = doc.xpath('//i[contains(@class,"fa-arrow-up") or contains(@class,"fa-upload")]/..//text()')
        for v in vals:
            m = re.search(r"(\d+)", str(v).strip())
            if m:
                ins.seeding = StringUtils.str_int(m.group(1))
                break

    if not ins.leeching:
        vals = doc.xpath('//i[contains(@class,"fa-arrow-down") or contains(@class,"fa-download")]/..//text()')
        for v in vals:
            m = re.search(r"(\d+)", str(v).strip())
            if m:
                ins.leeching = StringUtils.str_int(m.group(1))
                break
