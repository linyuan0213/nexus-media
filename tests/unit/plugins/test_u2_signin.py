"""U2 签到 cookie 失效判定测试（修复 login.php 链接误报）."""

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
