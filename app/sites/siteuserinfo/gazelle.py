"""Gazelle 架构用户信息解析"""
import re

from lxml import etree

from app.utils import StringUtils


def is_gazelle(ins):
    return "Powered by Gazelle" in ins._index_html or "DIC Music" in ins._index_html


def parse(ins):
    html_text = re.sub(r"#\d+", "", re.sub(r"\d+px", "", ins._index_html))
    html = etree.HTML(html_text)
    if html is None:
        return

    tmps = html.xpath('//a[contains(@href, "user.php?id=")]')
    if tmps:
        m = re.search(r"user.php\?id=(\d+)", tmps[0].attrib['href'])
        if m and m.group(1).strip():
            ins.userid = m.group(1)
            ins.username = tmps[0].text.strip()

    tmps = html.xpath('//*[@id="header-uploaded-value"]/@data-value')
    if tmps:
        ins.upload = StringUtils.num_filesize(tmps[0])
    else:
        tmps = html.xpath('//li[@id="stats_seeding"]/span/text()')
        if tmps:
            ins.upload = StringUtils.num_filesize(tmps[0])

    tmps = html.xpath('//*[@id="header-downloaded-value"]/@data-value')
    if tmps:
        ins.download = StringUtils.num_filesize(tmps[0])
    else:
        tmps = html.xpath('//li[@id="stats_leeching"]/span/text()')
        if tmps:
            ins.download = StringUtils.num_filesize(tmps[0])

    ins.ratio = 0.0 if ins.download <= 0.0 else round(ins.upload / ins.download, 3)

    tmps = html.xpath('//a[contains(@href, "bonus.php")]/@data-tooltip')
    if tmps:
        bm = re.search(r"([\d,.]+)", tmps[0])
        if bm and bm.group(1).strip():
            ins.bonus = StringUtils.str_float(bm.group(1))
    else:
        tmps = html.xpath('//a[contains(@href, "bonus.php")]')
        if tmps:
            bt = tmps[0].xpath("string(.)")
            bm = re.search(r"([\d,.]+)", bt)
            if bm and bm.group(1).strip():
                ins.bonus = StringUtils.str_float(bm.group(1))

    level = html.xpath('//*[@id="class-value"]/@data-value')
    if level:
        ins.user_level = level[0].strip()
    else:
        level = html.xpath('//li[contains(text(), "用户等级")]/text()')
        if level:
            ins.user_level = level[0].split(':')[1].strip()

    join = html.xpath('//*[@id="join-date-value"]/@data-value')
    if join:
        ins.join_at = StringUtils.unify_datetime_str(join[0].strip())
    else:
        join = html.xpath('//div[contains(@class,"box_userinfo_stats")]//li[contains(text(),"加入时间")]/span/text()')
        if join:
            ins.join_at = StringUtils.unify_datetime_str(join[0].strip())
