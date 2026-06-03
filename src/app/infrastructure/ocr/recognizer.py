import base64

from app.core.settings import settings
from app.infrastructure.http.auth import CookieAuth
from app.infrastructure.http.client import HttpClient
from app.infrastructure.http.config import HttpClientConfig


class OcrRecognizer:
    ocr_server_host = settings.get("laboratory").get("ocr_server_host")
    if ocr_server_host:
        ocr_server_host = ocr_server_host.removesuffix("/")
        _ocr_b64_url = ocr_server_host + "/ocr/base64"
    else:
        _ocr_b64_url = None

    def get_captcha_text(self, image_url=None, image_b64=None, cookie=None, ua=None):
        """
        根据图片地址，获取验证码图片，并识别内容
        :param image_url: 图片地址
        :param image_b64: 图片base64，跳过图片地址下载
        :param cookie: 下载图片使用的cookie
        :param ua: 下载图片使用的ua
        """

        if not self._ocr_b64_url:
            return ""

        if image_url:
            headers = {"User-Agent": ua} if ua else {}
            ret = HttpClient().get(image_url, headers=headers, auth=CookieAuth(cookie))
            image_bin = ret.content
            if not image_bin:
                return ""
            image_b64 = base64.b64encode(image_bin).decode()
        if not image_b64:
            return ""
        ret = HttpClient(config=HttpClientConfig(default_headers={"Content-Type": "application/json"})).post(
            url=self._ocr_b64_url, json={"image_b64": image_b64}
        )
        return ret.json().get("res")
