"""浏览器自动化通用签到处理器。"""

import re
import time

from lxml import etree

from app.infrastructure.chrome import BrowserSession
from app.sites.siteconf import SiteConf
from app.sites.utils import is_logged_in
from app.utils import ExceptionUtils
from app.utils.browser_mode import get_chrome_server_url

from .base import SigninResult, SiteSigninContext, SiteSigninHandler

_CHALLENGE_INDICATORS = re.compile(
    r"challenge|cf-browser|Checking your browser|DDoS|正在检查|请等待|验证您不是机器人|slg-bg|slg-box|雷池|安全拦截",
    re.IGNORECASE,
)
_PAGE_WAIT_TIMEOUT = 120
_PAGE_POLL_INTERVAL = 3


class BrowserSigninHandler(SiteSigninHandler):
    """浏览器自动化通用处理器。"""

    site_id = "__browser__"

    def __init__(self, plugin_ctx, rate_limiter, config: dict):
        super().__init__(plugin_ctx, rate_limiter)
        self._config = config

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        site_def = self._plugin_ctx.site_engine.get_by_id(ctx.site_id)
        home_url = self._resolve_home_url(site_def, ctx)

        server_url = get_chrome_server_url()
        if not server_url:
            return SigninResult.fail(site, "Chrome 服务器未配置")

        self._plugin_ctx.info(f"开始浏览器签到：{site}")
        try:
            with BrowserSession(site_key=site, server_url=server_url) as session:
                result = session.navigate(home_url, cookie=ctx.cookie)
                html_text = result.get("html", "")
                if not html_text:
                    return SigninResult.fail(site, "无法打开网站")

                html_text = self._wait_cloudflare(session, post_navigate=html_text)

                if self._already_signed(html_text):
                    return SigninResult.already(site)

                if not is_logged_in(html_text):
                    return SigninResult.fail(site, "登录状态异常")

                site_conf = SiteConf(self._plugin_ctx.site_engine)
                default_selectors = site_conf.get_checkin_conf()
                selectors = self._config.get("checkin_selectors") or default_selectors
                xpath = self._find_checkin_xpath(html_text, selectors)
                if not xpath:
                    return SigninResult.custom(True, f"[{site}]模拟登录成功")

                self._plugin_ctx.debug(f"{site} 点击签到按钮: {xpath}")
                session.click(f"xpath:{xpath}")
                html_text = self._wait_page_stable(session)

                if self._success(html_text):
                    return SigninResult.custom(True, f"[{site}]浏览器签到成功")
                if self._already_signed(html_text):
                    return SigninResult.already(site)
                if self._two_factor(html_text):
                    return SigninResult.fail(site, "需要两步验证")
                if self._error(html_text):
                    return SigninResult.fail(site, "页面显示错误")
                return SigninResult.fail(site, "浏览器签到失败，未知原因")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return SigninResult.fail(site, str(e))

    @staticmethod
    def _wait_cloudflare(session: BrowserSession, post_navigate: str) -> str:
        html_text = post_navigate
        deadline = time.monotonic() + _PAGE_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            if _CHALLENGE_INDICATORS.search(html_text):
                time.sleep(_PAGE_POLL_INTERVAL)
                html_text = session.html()
                continue
            return html_text
        return html_text

    @staticmethod
    def _wait_page_stable(session: BrowserSession) -> str:
        prev = ""
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            html_text = session.html()
            if html_text and html_text == prev:
                return html_text
            prev = html_text
            time.sleep(_PAGE_POLL_INTERVAL)
        return session.html()

    def _resolve_home_url(self, site_def, ctx: SiteSigninContext) -> str:
        if site_def and site_def.domain:
            domain = site_def.domain
            if not domain.startswith(("http://", "https://")):
                domain = f"https://{domain}"
            return domain.rstrip("/")
        return ctx.site_url.rstrip("/")

    def _find_checkin_xpath(self, html_text: str, selectors: list[str]) -> str | None:
        html = etree.HTML(html_text)
        if html is None:
            return None
        for xpath in selectors:
            if html.xpath(xpath):
                return xpath
        return None

    @staticmethod
    def _already_signed(text: str) -> bool:
        return bool(re.search(r"已签|签到已得|今日已签|已签到|签到成功", text, re.IGNORECASE))

    def _success(self, text: str) -> bool:
        markers = self._config.get("success_markers", [])
        if markers:
            return any(re.search(m, text, re.IGNORECASE) for m in markers)
        return bool(re.search(r"已签|签到成功|获得.*积分|签到.*积分", text, re.IGNORECASE))

    @staticmethod
    def _two_factor(text: str) -> bool:
        return bool(re.search(r"完成两步验证|两步验证|2FA|二次验证", text, re.IGNORECASE))

    @staticmethod
    def _error(text: str) -> bool:
        return bool(re.search(r"错误|失败|异常|error|fail", text, re.IGNORECASE))
