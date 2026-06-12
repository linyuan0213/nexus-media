import base64

from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.ocr import OcrRecognizer
from app.sites import engine_tools
from app.sites.engine import SiteEngine
from app.sites.site_cache import SiteCache
from app.utils import StringUtils


class SiteCookie:
    def __init__(
        self,
        sites: SiteCache,
        site_engine: SiteEngine,
        progress=None,
        siteconf=None,
        ocrhelper: OcrRecognizer | None = None,
    ):
        self.progress = progress
        self._site_engine = site_engine
        self.sites = sites
        self.siteconf = siteconf
        self.ocrhelper = ocrhelper or OcrRecognizer()
        self.captcha_code = {}

    def set_code(self, code, value):
        """
        设置验证码的值
        """
        self.captcha_code[code] = value

    def get_code(self, code):
        """
        获取验证码的值
        """
        return self.captcha_code.get(code)

    def get_captcha_text(self, chrome, code_url):
        """
        识别验证码图片的内容
        """
        code_b64 = self.get_captcha_base64(chrome=chrome, image_url=code_url)
        if not code_b64:
            return ""
        return self.ocrhelper.get_captcha_text(image_b64=code_b64) if self.ocrhelper else ""

    @staticmethod
    def __get_captcha_url(siteurl, imageurl):
        """
        获取验证码图片的URL
        """
        if not siteurl or not imageurl:
            return ""
        if imageurl.startswith("/"):
            imageurl = imageurl[1:]
        return f"{StringUtils.get_base_url(siteurl)}/{imageurl}"

    def get_captcha_base64(self, chrome, image_url):
        """
        根据图片地址，使用浏览器获取验证码图片base64编码
        """
        if not image_url:
            return ""
        engine = self._site_engine
        rate_limiter = getattr(engine, "site_limiter", None)
        rate_limiter_engine = rate_limiter.engine if rate_limiter else None
        site_def = engine.get_by_url(image_url)
        rl_kwargs = engine_tools._get_rate_limit_kwargs(engine, site_def)
        client = HttpClient(rate_limiter=rate_limiter_engine)
        ret = client.get(
            image_url, headers={"User-Agent": chrome.get_ua()}, auth=CookieAuth(chrome.get_cookies()), **rl_kwargs
        )
        return base64.b64encode(ret.content).decode()
