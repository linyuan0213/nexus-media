import re

from lxml import etree

from app.sites.utils import is_logged_in
from app.utils import ExceptionUtils, StringUtils
from app.infrastructure.chrome import ChromeClient
from app.sites.siteconf import SiteConf


class ChromeSigninSimulator:
    def __init__(self, site_conf=None, drissionpage_helper=None, site_engine=None):
        self._siteconf = site_conf or SiteConf(site_engine)
        self._drissionpage_helper = drissionpage_helper or ChromeClient()

    def signin(self, site_info: dict, plugin_ctx) -> str:
        site = site_info.get("name")
        site_url = site_info.get("signurl")
        site_cookie = site_info.get("cookie")

        chrome = self._drissionpage_helper
        if not site_url or not (chrome and chrome.get_status()):
            return ""

        plugin_ctx.info(f"开始站点仿真签到：{site}")
        home_url = StringUtils.get_base_url(site_url)
        if "1ptba" in home_url:
            home_url = f"{home_url}/index.php"

        html_text = chrome.get_page_html(url=home_url, cookies=site_cookie)
        if not html_text:
            plugin_ctx.warn(f"{site} 无法打开网站")
            return f"[{site}]仿真签到失败，无法打开网站！"

        if re.search(r"已签|签到已得|今日已签|已签到|签到成功", html_text, re.IGNORECASE):
            plugin_ctx.info(f"{site} 今日已签到")
            return f"[{site}]今日已签到"

        if re.search(r"完成两步验证", html_text, re.IGNORECASE):
            plugin_ctx.warn(f"{site} 仿真签到失败，需要两步验证")
            return f"[{site}]仿真签到失败，需要两步验证"

        if not is_logged_in(html_text):
            plugin_ctx.warn(f"{site} 仿真签到失败，登录状态异常")
            return f"[{site}]仿真签到失败，登录状态异常"

        html = etree.HTML(html_text)
        xpath_str = None
        for xpath in self._siteconf.get_checkin_conf():
            if html.xpath(xpath):
                xpath_str = xpath
                plugin_ctx.debug(f"{site} 找到签到按钮XPath: {xpath_str}")
                break

        if not xpath_str:
            plugin_ctx.warn(f"{site} 未找到签到按钮，但登录成功")
            return f"[{site}]模拟登录成功"

        try:
            plugin_ctx.debug(f"{site} 开始点击签到按钮")
            html_text = chrome.get_page_html(
                url=home_url, cookies=site_cookie, click_xpath=f"xpath:{xpath_str}", delay=10, click_delay=15
            )

            if not html_text:
                plugin_ctx.warn(f"{site} 仿真签到失败，无法通过Cloudflare")
                return f"[{site}]仿真签到失败，无法通过Cloudflare！"

            if re.search(r"已签|签到已得|签到成功|签到.*成功|获得.*积分|签到.*积分", html_text, re.IGNORECASE):
                plugin_ctx.info(f"{site} 仿真签到成功")
                return f"[{site}]仿真签到成功"
            elif re.search(r"完成两步验证|两步验证|2FA|二次验证", html_text, re.IGNORECASE):
                plugin_ctx.warn(f"{site} 仿真签到失败，需要两步验证")
                return f"[{site}]仿真签到失败，需要两步验证"
            elif re.search(r"已签到|今日已签|重复签到", html_text, re.IGNORECASE):
                plugin_ctx.info(f"{site} 今日已签到")
                return f"[{site}]今日已签到"
            else:
                if re.search(r"错误|失败|异常|error|fail", html_text, re.IGNORECASE):
                    plugin_ctx.warn(f"{site} 仿真签到失败，页面显示错误")
                    return f"[{site}]仿真签到失败，页面显示错误"
                else:
                    plugin_ctx.warn(f"{site} 仿真签到失败，未知原因")
                    return f"[{site}]仿真签到失败，未知原因"
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            plugin_ctx.warn(f"{site} 仿真签到失败：{str(e)}")
            return f"[{site}]签到失败！"
