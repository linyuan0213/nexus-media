"""Discuz 架构用户信息解析"""
import re
from lxml import etree
from app.utils import StringUtils


def is_discuz(ins):
    return 'Powered by Discuz!' in ins._index_html


def parse(ins):
    html_text = re.sub(r"#\d+", "", re.sub(r"\d+px", "", ins._index_html))
    html = etree.HTML(html_text)
    if html is None:
        return

    user_info = html.xpath('//a[contains(@href, "&uid=")]')
    if user_info:
        m = re.search(r"&uid=(\d+)", user_info[0].attrib['href'])
        if m and m.group(1).strip():
            ins.userid = m.group(1)
            ins.username = user_info[0].text.strip()

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
        ins.upload = StringUtils.num_filesize(upload[0].strip().split('/')[-1])

    download = html.xpath('//li[em[contains(text(),"下载量")]]/text()')
    if download:
        ins.download = StringUtils.num_filesize(download[0].strip().split('/')[-1])

    ins.ratio = 0.0 if ins.download <= 0.0 else round(ins.upload / ins.download, 3)
