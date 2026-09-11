"""U2 签到处理器。"""

import re
from datetime import datetime

from app.infrastructure.http.auth import CookieAuth
from app.utils import StringUtils

from .base import SigninResult, SiteSigninContext, SiteSigninHandler


class U2(SiteSigninHandler):
    site_id = "u2"
    _ALREADY_REGEXS = [
        r'<a href="showup.php">已签到</a>',
        r'<a href="showup.php">Show Up</a>',
        r'<a href="showup.php">Показать</a>',
        r'<a href="showup.php">已簽到</a>',
    ]
    _SUCCESS_TEXT = "window.location.href = 'showup.php';\u003c/script\u003e"

    def signin(self, ctx: SiteSigninContext) -> SigninResult:
        site = ctx.site
        if not ctx.cookie:
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)

        if datetime.now().hour < 9:
            # 未到开放时间：不判失败，等待 9 点后的调度轮次补签
            return SigninResult.custom(False, f"[{site}]9点后开放签到，本次跳过")

        base_url = StringUtils.get_base_url(ctx.site_url)
        showup_url = base_url + "/showup.php"
        base_headers = {"User-Agent": ctx.ua} if ctx.ua else {}
        post_headers = {**base_headers, "Referer": showup_url, "Origin": base_url}

        with self._http_client(ctx) as client:
            try:
                index_res = client.get(
                    url=showup_url,
                    headers=base_headers,
                    auth=CookieAuth(ctx.cookie),
                )
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 首页请求失败: {e}")
                return SigninResult.fail(site, SigninResult.SITE_UNREACHABLE)

        text = index_res.text
        if self._is_cookie_expired(text, str(index_res.url)):
            return SigninResult.fail(site, SigninResult.COOKIE_EXPIRED)
        if self.sign_in_result(text, self._ALREADY_REGEXS):
            return SigninResult.already(site)

        data = self._build_signin_data(text)
        if not data:
            return SigninResult.fail(site, "未获取到签到参数")

        with self._http_client(ctx) as client:
            try:
                sign_res = client.post(
                    url=showup_url + "?action=show",
                    data=data,
                    headers=post_headers,
                    auth=CookieAuth(ctx.cookie),
                )
            except Exception as e:
                self._plugin_ctx.warn(f"{site} 签到请求失败: {e}")
                return SigninResult.fail(site, SigninResult.REQUEST_FAILED)

        if self._SUCCESS_TEXT in sign_res.text:
            return SigninResult.success(site)

        # 验证码选错也会记录出勤（"错误"仅代表选番剧小游戏答错），
        # 因此以再次请求首页是否显示"已签到"作为最终判定。
        with self._http_client(ctx) as client:
            try:
                verify_res = client.get(
                    url=showup_url,
                    headers=base_headers,
                    auth=CookieAuth(ctx.cookie),
                )
            except Exception:  # noqa: BLE001
                return SigninResult.fail(site, "签到结果校验失败")
        if self.sign_in_result(verify_res.text, self._ALREADY_REGEXS):
            return SigninResult.success(site)
        return SigninResult.fail(site, "签到失败，未知原因")

    def _build_signin_data(self, text: str) -> dict | None:
        """构造签到表单数据。

        U2 的 showup 表单必须携带 `_csrf`（否则 403 Invalid or expired link），
        且提交按钮中混有非签到按钮（如 shout），只能从 `captcha_*` 选项里选。
        验证码答错不影响出勤，任选一个候选即可。
        """
        params = self._extract_form_params(text)
        if not params:
            return None
        req, hash_str, form, submit_names, submit_values = params
        captcha_options = [
            (name, value) for name, value in zip(submit_names, submit_values) if name.startswith("captcha_")
        ]
        if not captcha_options:
            return None
        submit_name, submit_value = captcha_options[0]
        data = {
            "_csrf": self._extract_input(text, "_csrf") or "",
            "req": req,
            "hash": hash_str,
            "form": form,
            "message": "一切随缘~",
            submit_name: submit_value,
        }
        return data

    @staticmethod
    def _is_cookie_expired(text: str, final_url: str = "") -> bool:
        """判定 U2 会话是否失效.

        不能仅凭页面含 `login.php` 链接判断——已登录的签到页同样带有该链接。
        以登录表单（password 输入）且无登出/用户页链接，或跳转门户登录页为准。
        """
        is_login_page = 'name="password"' in text and "logout.php" not in text and "userdetails.php" not in text
        redirected_to_login = "portal.php" in final_url and "returnto=" in final_url
        return is_login_page or redirected_to_login

    def _extract_form_params(self, text: str) -> tuple | None:
        req = self._extract_input(text, "req")
        hash_str = self._extract_input(text, "hash")
        form = self._extract_input(text, "form")
        submit_names = re.findall(r'<input[^\u003e]*type=["\']submit["\'][^\u003e]*name=["\']([^"\']+)["\']', text)
        submit_values = re.findall(r'<input[^\u003e]*type=["\']submit["\'][^\u003e]*value=["\']([^"\']+)["\']', text)
        if not req or not hash_str or not form or not submit_names or not submit_values:
            return None
        return req, hash_str, form, submit_names, submit_values

    @staticmethod
    def _extract_input(text: str, name: str) -> str | None:
        m = re.search(rf'<input[^\u003e]*name=["\']{name}["\'][^\u003e]*value=["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
        return None
