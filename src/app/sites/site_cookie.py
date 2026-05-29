import base64

from app.helper import OcrHelper
from app.utils import RequestUtils, StringUtils
from app.di import container


class SiteCookie:
    def __init__(self, progress=None, sites=None, siteconf=None, ocrhelper=None):
        self.progress = progress or container.progress_helper()
        self.sites = sites or container.sites()
        self.siteconf = siteconf or container.site_conf()
        self.ocrhelper = ocrhelper or OcrHelper()
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

    @staticmethod
    def get_captcha_base64(chrome, image_url):
        """
        根据图片地址，使用浏览器获取验证码图片base64编码
        """
        if not image_url:
            return ""
        ret = RequestUtils(headers=chrome.get_ua(), cookies=chrome.get_cookies()).get_res(image_url)
        if ret:
            return base64.b64encode(ret.content).decode()
        return ""
