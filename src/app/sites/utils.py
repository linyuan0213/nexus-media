"""站点通用工具."""

import json

from lxml import etree

from app.utils import JsonUtils


def is_logged_in(html_text: str) -> bool:
    """判断站点是否已经登录."""
    if JsonUtils.is_valid_json(html_text):
        json_data = json.loads(html_text)
        message = json_data.get("message")
        success = json_data.get("success")
        error_message = json_data.get("errorMessage")
        return bool(message and message.upper() == "SUCCESS" or success or error_message and "已签" in error_message)
    if "签到成功" in html_text:
        return True

    html = etree.HTML(html_text)
    if not html:
        return False
    if html.xpath("//input[@type='password']"):
        return False
    xpaths = [
        '//a[contains(@href, "logout")'
        ' or contains(@data-url, "logout")'
        ' or contains(@href, "mybonus") '
        ' or contains(@onclick, "logout")'
        ' or contains(@href, "usercp")]',
        '//form[contains(@action, "logout")]',
    ]
    for xpath in xpaths:
        if html.xpath(xpath):
            return True
    user_info_div = html.xpath('//div[@class="user-info-side"]')
    if user_info_div:
        return True
    x_csrf_token = html.xpath("//head/meta[contains(@name, 'x-csrf-token')]")
    return bool(x_csrf_token)
