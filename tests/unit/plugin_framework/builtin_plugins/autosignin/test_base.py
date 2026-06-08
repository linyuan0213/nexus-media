from unittest.mock import MagicMock

import pytest

from app.plugin_framework.builtin_plugins.autosignin.backend.handlers.base import (
    SigninResult,
    SiteSigninHandler,
)


class TestSigninResult:
    def test_success(self):
        r = SigninResult.success("test_site")
        assert r.ok is True
        assert r.msg == "[test_site]签到成功"

    def test_already(self):
        r = SigninResult.already("test_site")
        assert r.ok is True
        assert r.msg == "[test_site]今日已签到"

    def test_fail(self):
        r = SigninResult.fail("test_site", "cookie失效")
        assert r.ok is False
        assert r.msg == "[test_site]签到失败，cookie失效"

    def test_custom(self):
        r = SigninResult.custom(True, "custom message")
        assert r.ok is True
        assert r.msg == "custom message"

    def test_signin_result_attrs(self):
        assert SigninResult.SUCCESS == "签到成功"
        assert SigninResult.ALREADY == "已签到"
        assert SigninResult.COOKIE_EXPIRED == "cookie失效"
        assert SigninResult.SITE_UNREACHABLE == "请检查站点连通性"
        assert SigninResult.REQUEST_FAILED == "签到接口请求失败"


class TestSiteSigninHandler:
    def test_check_cookie_expired(self):
        class DummyHandler(SiteSigninHandler):
            def signin(self, ctx):
                return SigninResult.custom(True, "")

        result = DummyHandler(MagicMock())._check_cookie("login.php in text", "test_site")
        assert result is not None
        assert result.ok is False
        assert "cookie失效" in result.msg

    def test_check_cookie_ok(self):
        class DummyHandler(SiteSigninHandler):
            def signin(self, ctx):
                return SigninResult.custom(True, "")

        result = DummyHandler(MagicMock())._check_cookie("<html>normal page</html>", "test_site")
        assert result is None

    @pytest.mark.parametrize(
        "html_res,regexs,expected",
        [
            ("已签到", ["已签到"], True),
            ("not matched", ["已签到"], False),
            ("签到成功", ["签到成功", "已签到"], True),
            ("今日已签到", ["签到成功"], False),
        ],
    )
    def test_sign_in_result(self, html_res, regexs, expected):
        result = SiteSigninHandler.sign_in_result(html_res, regexs)
        assert result == expected
