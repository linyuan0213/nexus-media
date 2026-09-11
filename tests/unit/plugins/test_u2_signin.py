"""U2 签到 cookie 失效判定测试（修复 login.php 链接误报）."""

from unittest.mock import MagicMock

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.u2 import U2

# 已登录的签到页：含 login.php 链接，但有登出/用户页、无密码表单
LOGGED_IN = """
<title>U2分享園@動漫花園 :: 每日签到</title>
<a href="logout.php">登出</a>
<a href="userdetails.php?id=1">我的</a>
<a href="login.php">登录</a>
<input name="req" /><input name="hash" />
"""

# 未登录跳转的门户页：有密码输入、无登出
LOGIN_PAGE = """
<title>Access Point :: U2</title>
<input name="username" /><input name="password" />
<a href="login.php">登录</a>
"""


class TestU2CookieExpired:
    def test_logged_in_with_login_link_not_expired(self):
        assert U2._is_cookie_expired(LOGGED_IN, "https://u2.dmhy.org/showup.php") is False

    def test_login_form_detected_expired(self):
        assert U2._is_cookie_expired(LOGIN_PAGE, "https://u2.dmhy.org/portal.php") is True

    def test_redirect_to_portal_detected_expired(self):
        url = "https://u2.dmhy.org/portal.php?returnto=showup.php"
        assert U2._is_cookie_expired(LOGGED_IN, url) is True

    def test_showup_page_url_not_expired(self):
        assert U2._is_cookie_expired(LOGGED_IN, "https://u2.dmhy.org/showup.php") is False


FORM_HTML = """
<form action="showup.php?action=show" method="post">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN" />
  <input type="hidden" name="req" value="REQ_TOKEN" />
  <input type="hidden" name="hash" value="HASH_TOKEN" />
  <input type="hidden" name="form" value="FORM_TOKEN" />
  <input type="submit" name="shout" value="喊话" />
  <input type="submit" name="captcha_aaa" value="Title A" />
  <input type="submit" name="captcha_bbb" value="Title B" />
</form>
"""


class TestU2SigninData:
    def _handler(self):
        return U2(MagicMock())

    def test_includes_csrf_and_tokens(self):
        data = self._handler()._build_signin_data(FORM_HTML)
        assert data is not None
        assert data["_csrf"] == "CSRF_TOKEN"
        assert data["req"] == "REQ_TOKEN"
        assert data["hash"] == "HASH_TOKEN"
        assert data["form"] == "FORM_TOKEN"

    def test_only_captcha_submit_selected(self):
        data = self._handler()._build_signin_data(FORM_HTML)
        assert data is not None
        captcha_keys = [k for k in data if k.startswith("captcha_")]
        assert len(captcha_keys) == 1
        assert "shout" not in data

    def test_missing_form_returns_none(self):
        assert self._handler()._build_signin_data("<html>no form</html>") is None
