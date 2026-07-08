"""站点通用工具."""

from lxml import etree

from app.utils import JsonUtils


def is_logged_in(html_text: str) -> bool:
    """判断站点是否已经登录."""
    if JsonUtils.is_valid_json(html_text):
        json_data = JsonUtils.loads(html_text)
        if not isinstance(json_data, dict):
            return False
        message = json_data.get("message")
        success = json_data.get("success")
        error_message = json_data.get("errorMessage")
        if message and str(message).upper() == "SUCCESS":
            return True
        if success:
            return True
        if error_message and "已签" in str(error_message):
            return True
        # 兼容 {"code":0/"0",...} 或 {"status":200,...} 且带有效 data 的成功响应（如朱雀）
        code = json_data.get("code")
        status = json_data.get("status")
        data = json_data.get("data")
        if data and (str(code) in ("0", "200") or str(status) in ("0", "200")):
            return True
        return False
    if "签到成功" in html_text:
        return True

    html = etree.HTML(html_text)
    if html is None:
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
